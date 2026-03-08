from __future__ import annotations

import hashlib
import json
import logging
import os
import ssl
import traceback
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen
from uuid import UUID

from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.core.logging import log_event
from app.models import (
    AnalysisJob,
    ClassificationResult,
    Company,
    CrawlArtifact,
    CrawlJob,
    Prompt,
    Run,
    ScrapeJob,
    ScrapePage,
)
from app.models.pipeline import AnalysisJobState, CrawlJobState, PredictedLabel, RunStatus


logger = logging.getLogger(__name__)

ANALYSIS_PAGE_ORDER = ("home", "about", "products")
MAX_CHARS_PER_PAGE = 12000
MAX_TOTAL_CONTEXT_CHARS = 30000


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {}
    except Exception:  # noqa: BLE001
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        decoded = json.loads(raw[start : end + 1])
        return decoded if isinstance(decoded, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def normalize_predicted_label(raw: str) -> PredictedLabel:
    normalized = (raw or "").strip().lower()
    if normalized == "possible":
        return PredictedLabel.POSSIBLE
    if normalized == "crap":
        return PredictedLabel.CRAP
    return PredictedLabel.UNKNOWN


def clamp_confidence(raw: Any) -> float | None:
    try:
        value = float(raw)
    except Exception:  # noqa: BLE001
        return None
    return max(0.0, min(1.0, value))


class AnalysisService:
    def __init__(self) -> None:
        self._openrouter_key = (settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()

    def create_runs(
        self,
        *,
        session: Session,
        companies: list[Company],
        prompt_id: UUID,
        general_model: str,
        classify_model: str,
        ocr_model: str,
    ) -> tuple[list[Run], list[AnalysisJob], list[UUID]]:
        prompt = session.get(Prompt, prompt_id)
        if not prompt:
            raise ValueError("Prompt not found.")
        if not prompt.enabled:
            raise ValueError("Selected prompt is disabled.")

        grouped: dict[UUID, list[Company]] = {}
        skipped_company_ids: list[UUID] = []
        queued_runs: list[Run] = []
        queued_jobs: list[AnalysisJob] = []

        for company in companies:
            latest_scrape = self._latest_completed_scrape_job(session=session, normalized_url=company.normalized_url)
            if latest_scrape is None:
                skipped_company_ids.append(company.id)
                continue
            grouped.setdefault(company.upload_id, []).append(company)

        prompt_hash = hashlib.sha256(prompt.prompt_text.encode("utf-8")).hexdigest()
        for upload_id, grouped_companies in grouped.items():
            run = Run(
                upload_id=upload_id,
                prompt_id=prompt.id,
                general_model=general_model,
                classify_model=classify_model,
                ocr_model=ocr_model,
                status=RunStatus.RUNNING,
                total_jobs=0,
                completed_jobs=0,
                failed_jobs=0,
                started_at=utcnow(),
            )
            session.add(run)
            session.flush()

            for company in grouped_companies:
                latest_scrape = self._latest_completed_scrape_job(session=session, normalized_url=company.normalized_url)
                if latest_scrape is None:
                    skipped_company_ids.append(company.id)
                    continue
                crawl_artifact = self._ensure_crawl_adapter(
                    session=session,
                    company=company,
                    scrape_job=latest_scrape,
                )
                analysis_job = AnalysisJob(
                    run_id=run.id,
                    upload_id=company.upload_id,
                    company_id=company.id,
                    crawl_artifact_id=crawl_artifact.id,
                    state=AnalysisJobState.QUEUED,
                    terminal_state=False,
                    prompt_hash=prompt_hash,
                )
                session.add(analysis_job)
                session.flush()
                queued_jobs.append(analysis_job)

            run.total_jobs = sum(1 for job in queued_jobs if job.run_id == run.id)
            queued_runs.append(run)

        session.commit()
        for run in queued_runs:
            session.refresh(run)
        for job in queued_jobs:
            session.refresh(job)
        return queued_runs, queued_jobs, skipped_company_ids

    # Error codes that are permanent (data missing, config wrong).
    # Everything else is treated as transient and will be retried.
    _PERMANENT_ERROR_CODES: frozenset[str] = frozenset({
        "analysis_dependencies_missing",
        "analysis_api_key_missing",
        "scrape_missing",
        "analysis_context_empty",
    })

    def run_analysis_job(self, *, session: Session, analysis_job_id: UUID) -> AnalysisJob:
        analysis_job = session.get(AnalysisJob, analysis_job_id)
        if not analysis_job:
            raise ValueError("Analysis job not found.")

        run = session.get(Run, analysis_job.run_id)
        prompt = session.get(Prompt, run.prompt_id) if run else None
        company = session.get(Company, analysis_job.company_id)
        if not run or not prompt or not company:
            analysis_job.state = AnalysisJobState.FAILED
            analysis_job.terminal_state = True
            analysis_job.last_error_code = "analysis_dependencies_missing"
            analysis_job.last_error_message = "Run, prompt, or company missing."
            analysis_job.finished_at = utcnow()
            session.add(analysis_job)
            session.commit()
            self._refresh_run_status(session=session, run_id=analysis_job.run_id)
            return analysis_job

        analysis_job.attempt_count += 1
        analysis_job.state = AnalysisJobState.RUNNING
        analysis_job.started_at = analysis_job.started_at or utcnow()
        analysis_job.last_error_code = None
        analysis_job.last_error_message = None
        session.add(analysis_job)
        session.commit()

        latest_scrape = self._latest_completed_scrape_job(session=session, normalized_url=company.normalized_url)
        if latest_scrape is None:
            return self._fail_job(
                session=session,
                analysis_job=analysis_job,
                error_code="scrape_missing",
                error_message="No completed scrape job found for company.",
            )

        pages = self._analysis_pages_for_job(session=session, job_id=latest_scrape.id)
        context = self._build_context(pages)
        if not context:
            return self._fail_job(
                session=session,
                analysis_job=analysis_job,
                error_code="analysis_context_empty",
                error_message="No markdown content found for analysis.",
            )

        rendered_prompt = self._render_prompt(
            prompt_text=prompt.prompt_text,
            domain=company.domain,
            context=context,
        )
        raw_response, llm_error = self._call_openrouter(model=run.classify_model, user_prompt=rendered_prompt)
        if llm_error or not raw_response:
            return self._fail_job(
                session=session,
                analysis_job=analysis_job,
                error_code=llm_error or "analysis_llm_failed",
                error_message="Classification model returned no response.",
            )

        payload = extract_json_object(raw_response)
        predicted_label = normalize_predicted_label(str(payload.get("predicted_label", "")))
        confidence = clamp_confidence(payload.get("confidence"))
        reasoning = {
            "priority_score": payload.get("priority_score"),
            "signals": payload.get("signals"),
            "other_fields": payload.get("other_fields"),
            "raw_response": raw_response,
        }
        evidence = payload.get("evidence")

        existing_result = session.exec(
            select(ClassificationResult).where(col(ClassificationResult.analysis_job_id) == analysis_job.id)
        ).first()
        if existing_result:
            existing_result.predicted_label = predicted_label
            existing_result.confidence = confidence
            existing_result.reasoning_json = reasoning
            existing_result.evidence_json = {"evidence": evidence}
            session.add(existing_result)
        else:
            session.add(
                ClassificationResult(
                    analysis_job_id=analysis_job.id,
                    predicted_label=predicted_label,
                    confidence=confidence,
                    reasoning_json=reasoning,
                    evidence_json={"evidence": evidence},
                )
            )

        analysis_job.state = AnalysisJobState.SUCCEEDED
        analysis_job.terminal_state = True
        analysis_job.finished_at = utcnow()
        session.add(analysis_job)
        session.commit()
        self._refresh_run_status(session=session, run_id=run.id)
        session.refresh(analysis_job)
        return analysis_job

    def _latest_completed_scrape_job(self, *, session: Session, normalized_url: str) -> ScrapeJob | None:
        return session.exec(
            select(ScrapeJob)
            .where(
                (col(ScrapeJob.normalized_url) == normalized_url)
                & (
                    (col(ScrapeJob.status) == "completed")
                    | (col(ScrapeJob.stage2_status) == "completed")
                )
            )
            .order_by(col(ScrapeJob.created_at).desc())
        ).first()

    def _analysis_pages_for_job(self, *, session: Session, job_id: UUID) -> list[ScrapePage]:
        pages = list(
            session.exec(
                select(ScrapePage)
                .where(col(ScrapePage.job_id) == job_id)
                .order_by(col(ScrapePage.depth).asc(), col(ScrapePage.id).asc())
            )
        )
        ordered: list[ScrapePage] = []
        for page_kind in ANALYSIS_PAGE_ORDER:
            ordered.extend([page for page in pages if page.page_kind == page_kind])
        ordered.extend([page for page in pages if page.page_kind not in ANALYSIS_PAGE_ORDER])
        return ordered

    def _build_context(self, pages: list[ScrapePage]) -> str:
        parts: list[str] = []
        total_chars = 0
        for page in pages:
            markdown = (page.markdown_content or "").strip()
            if not markdown:
                continue
            chunk = markdown[:MAX_CHARS_PER_PAGE]
            block = f"## {page.page_kind.upper()} PAGE\nURL: {page.url}\n\n{chunk}"
            projected = total_chars + len(block)
            if projected > MAX_TOTAL_CONTEXT_CHARS and parts:
                break
            parts.append(block)
            total_chars += len(block)
        return "\n\n".join(parts).strip()

    def _render_prompt(self, *, prompt_text: str, domain: str, context: str) -> str:
        rendered = prompt_text.replace("{domain}", domain)
        rendered = rendered.replace("{org}", domain)
        rendered = rendered.replace("{context}", context)
        return rendered

    def _call_openrouter(self, *, model: str, user_prompt: str) -> tuple[str, str]:
        if not self._openrouter_key:
            return "", "analysis_api_key_missing"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return strict JSON only. Follow the provided rubric exactly.",
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            url=f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
        )
        try:
            with urlopen(request, context=ssl.create_default_context(), timeout=120) as response:  # noqa: S310
                raw = response.read().decode("utf-8", errors="ignore")
            decoded = json.loads(raw)
            choices = decoded.get("choices") or []
            if not choices:
                log_event(logger, "analysis_llm_empty_choices", model=model, raw_response=raw[:500])
                return "", "analysis_llm_failed"
            content = choices[0]["message"]["content"]
            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and str(item.get("type", "")) == "text":
                        text_parts.append(str(item.get("text", "")))
                return "\n".join(part for part in text_parts if part).strip(), ""
            return str(content or "").strip(), ""
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "analysis_llm_error", model=model, error=str(exc), traceback=traceback.format_exc())
            return "", "analysis_llm_failed"

    def _ensure_crawl_adapter(self, *, session: Session, company: Company, scrape_job: ScrapeJob) -> CrawlArtifact:
        # Derive the actual crawl state from the scrape job outcome.
        actual_state = (
            CrawlJobState.SUCCEEDED
            if scrape_job.status == "completed" and scrape_job.pages_fetched_count > 0
            else CrawlJobState.FAILED
        )
        crawl_job = session.exec(
            select(CrawlJob)
            .where(
                (col(CrawlJob.upload_id) == company.upload_id)
                & (col(CrawlJob.company_id) == company.id)
            )
        ).first()
        if crawl_job is None:
            crawl_job = CrawlJob(
                upload_id=company.upload_id,
                company_id=company.id,
                state=actual_state,
                attempt_count=1,
                started_at=scrape_job.step1_started_at or scrape_job.created_at,
                finished_at=scrape_job.step2_finished_at or scrape_job.updated_at,
            )
            session.add(crawl_job)
            session.flush()
        else:
            crawl_job.state = actual_state
            crawl_job.finished_at = scrape_job.step2_finished_at or scrape_job.updated_at
            crawl_job.updated_at = utcnow()
            session.add(crawl_job)
            session.flush()

        pages = self._analysis_pages_for_job(session=session, job_id=scrape_job.id)
        pages_by_kind = {page.page_kind: page for page in pages}
        artifact = session.exec(
            select(CrawlArtifact)
            .where(col(CrawlArtifact.crawl_job_id) == crawl_job.id)
            .order_by(col(CrawlArtifact.created_at).desc())
        ).first()
        if artifact is None:
            artifact = CrawlArtifact(
                company_id=company.id,
                crawl_job_id=crawl_job.id,
            )
        artifact.home_url = pages_by_kind.get("home").url if pages_by_kind.get("home") else None
        artifact.about_url = pages_by_kind.get("about").url if pages_by_kind.get("about") else None
        artifact.product_url = pages_by_kind.get("products").url if pages_by_kind.get("products") else None
        artifact.home_status = pages_by_kind.get("home").status_code if pages_by_kind.get("home") else None
        artifact.about_status = pages_by_kind.get("about").status_code if pages_by_kind.get("about") else None
        artifact.product_status = pages_by_kind.get("products").status_code if pages_by_kind.get("products") else None
        session.add(artifact)
        session.flush()
        return artifact

    def _fail_job(self, *, session: Session, analysis_job: AnalysisJob, error_code: str, error_message: str) -> AnalysisJob:
        is_permanent = error_code in self._PERMANENT_ERROR_CODES
        attempts_exhausted = analysis_job.attempt_count >= analysis_job.max_attempts

        if is_permanent or attempts_exhausted:
            # Terminal failure: permanent error or no retries left.
            analysis_job.state = AnalysisJobState.DEAD if attempts_exhausted and not is_permanent else AnalysisJobState.FAILED
            analysis_job.terminal_state = True
            analysis_job.finished_at = utcnow()
        else:
            # Transient failure with retries remaining: put back to QUEUED.
            # The worker will re-enqueue this job for another attempt.
            analysis_job.state = AnalysisJobState.QUEUED
            analysis_job.terminal_state = False

        analysis_job.last_error_code = error_code
        analysis_job.last_error_message = error_message
        session.add(analysis_job)
        session.commit()
        if analysis_job.terminal_state:
            self._refresh_run_status(session=session, run_id=analysis_job.run_id)
        session.refresh(analysis_job)
        return analysis_job

    def _refresh_run_status(self, *, session: Session, run_id: UUID) -> None:
        run = session.get(Run, run_id)
        if not run or run.total_jobs == 0:
            return

        # Use separate COUNT queries + ORM assignment. The correlated-subquery
        # UPDATE approach fails silently in SQLite due to expression type coercion.
        succeeded = session.exec(
            select(func.count())
            .select_from(AnalysisJob)
            .where(
                (col(AnalysisJob.run_id) == run_id)
                & (col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED)
            )
        ).one() or 0
        failed = session.exec(
            select(func.count())
            .select_from(AnalysisJob)
            .where(
                (col(AnalysisJob.run_id) == run_id)
                & col(AnalysisJob.state).in_([AnalysisJobState.FAILED, AnalysisJobState.DEAD])
            )
        ).one() or 0
        terminal = session.exec(
            select(func.count())
            .select_from(AnalysisJob)
            .where(
                (col(AnalysisJob.run_id) == run_id)
                & col(AnalysisJob.terminal_state).is_(True)
            )
        ).one() or 0

        run.completed_jobs = succeeded
        run.failed_jobs = failed
        is_done = terminal >= run.total_jobs
        if is_done:
            run.status = RunStatus.FAILED if failed > 0 else RunStatus.COMPLETED
            if not run.finished_at:
                run.finished_at = utcnow()
        else:
            run.status = RunStatus.RUNNING
        session.add(run)
        session.commit()
