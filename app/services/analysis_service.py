from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, func, select

from app.core.logging import log_event
from app.services.llm_client import LLMClient, ERR_API_KEY_MISSING, ERR_RATE_LIMITED
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

# Controls context assembly order for the classification prompt.
# Pages are sorted by this order; any page kind not listed is appended after.
ANALYSIS_PAGE_ORDER = ("home", "about", "products", "contact", "team", "leadership", "services")

_analysis_llm = LLMClient(purpose="analysis", min_interval_sec=0.5)
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
    def create_runs(
        self,
        *,
        session: Session,
        companies: list[Company],
        prompt_id: UUID,
        general_model: str,
        classify_model: str,
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

        # Flush (not commit) so the caller can atomically add outbox rows in
        # the same transaction before committing.
        session.flush()
        for run in queued_runs:
            session.refresh(run)
        for job in queued_jobs:
            session.refresh(job)
        return queued_runs, queued_jobs, skipped_company_ids

    # Error codes that are permanent — skip all Celery retries.
    # Rate-limited is permanent here because LLMClient already exhausted its internal retries;
    # further job-level retries would just hammer the API again immediately.
    _PERMANENT_ERROR_CODES: frozenset[str] = frozenset({
        "analysis_dependencies_missing",
        "analysis_api_key_missing",
        "analysis_llm_rate_limited",
        "scrape_missing",
        "analysis_context_empty",
    })

    # Map LLMClient error codes → analysis domain error codes.
    _LLM_ERROR_MAP: dict[str, str] = {
        ERR_API_KEY_MISSING: "analysis_api_key_missing",
        ERR_RATE_LIMITED:    "analysis_llm_rate_limited",
    }

    def run_analysis_job(self, *, engine: Any, analysis_job_id: UUID) -> AnalysisJob | None:
        """Run classification for a single AnalysisJob.

        Uses two short-lived DB sessions so the connection is not held open
        during the (potentially long) LLM call.
        """
        _ANALYSIS_LOCK_TTL = timedelta(minutes=20)  # generous buffer above worst-case LLM latency

        # ── Phase 1: CAS-claim + load all context ──────────────────────────
        now = utcnow()
        lock_token = str(uuid4())
        with Session(engine) as session:
            session.execute(
                sa_update(AnalysisJob)
                .where(
                    col(AnalysisJob.id) == analysis_job_id,
                    col(AnalysisJob.terminal_state).is_(False),
                    col(AnalysisJob.state).in_([AnalysisJobState.QUEUED, AnalysisJobState.RUNNING]),
                    or_(
                        col(AnalysisJob.lock_token).is_(None),
                        col(AnalysisJob.lock_expires_at) < now,
                    ),
                )
                .values(
                    state=AnalysisJobState.RUNNING,
                    attempt_count=col(AnalysisJob.attempt_count) + 1,
                    lock_token=lock_token,
                    lock_expires_at=now + _ANALYSIS_LOCK_TTL,
                    last_error_code=None,
                    last_error_message=None,
                    updated_at=now,
                )
            )
            session.commit()
            analysis_job = session.get(AnalysisJob, analysis_job_id)
            if not analysis_job or analysis_job.lock_token != lock_token:
                log_event(logger, "analysis_skipped_not_owner", analysis_job_id=str(analysis_job_id))
                return None

            # Set started_at only on the first attempt.
            if not analysis_job.started_at:
                analysis_job.started_at = now
                session.add(analysis_job)
                session.commit()

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

            latest_scrape = self._latest_completed_scrape_job(session=session, normalized_url=company.normalized_url)

            # Capture values needed after session closes.
            run_id = run.id
            attempt_count = analysis_job.attempt_count
            max_attempts = analysis_job.max_attempts
            early_fail: tuple[str, str] | None = None

            if latest_scrape is None:
                early_fail = ("scrape_missing", "No completed scrape job found for company.")
                classify_model = ""
                rendered_prompt = ""
            else:
                pages = self._analysis_pages_for_job(session=session, job_id=latest_scrape.id)
                context = self._build_context(pages)
                if not context:
                    early_fail = ("analysis_context_empty", "No markdown content found for analysis.")
                    classify_model = ""
                    rendered_prompt = ""
                else:
                    classify_model = run.classify_model
                    rendered_prompt = self._render_prompt(
                        prompt_text=prompt.prompt_text,
                        domain=company.domain,
                        context=context,
                    )
        # ── session closed; connection returned to pool ──────────────────────

        if early_fail:
            return self._fail_job(
                engine=engine,
                analysis_job_id=analysis_job_id,
                error_code=early_fail[0],
                error_message=early_fail[1],
                lock_token=lock_token,
                run_id=run_id,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            )

        # ── Phase 2: LLM call (no DB session held) ───────────────────────────
        raw_response, llm_error = _analysis_llm.chat(
            model=classify_model,
            messages=[
                {"role": "system", "content": "Return strict JSON only. Follow the provided rubric exactly."},
                {"role": "user", "content": rendered_prompt},
            ],
            response_format={"type": "json_object"},
        )

        if llm_error or not raw_response:
            error_code = self._LLM_ERROR_MAP.get(llm_error, "analysis_llm_failed") if llm_error else "analysis_llm_failed"
            return self._fail_job(
                engine=engine,
                analysis_job_id=analysis_job_id,
                error_code=error_code,
                error_message="Classification model returned no response.",
                lock_token=lock_token,
                run_id=run_id,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            )

        # ── Phase 3: write result (new short-lived session) ──────────────────
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

        with Session(engine) as session:
            # Re-verify ownership (guards against lock TTL expiry during LLM call).
            analysis_job = session.get(AnalysisJob, analysis_job_id)
            if not analysis_job or analysis_job.lock_token != lock_token:
                log_event(logger, "analysis_results_skipped_not_owner", analysis_job_id=str(analysis_job_id))
                return None

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
            self._refresh_run_status(session=session, run_id=run_id)
            session.refresh(analysis_job)
            return analysis_job

    def _latest_completed_scrape_job(self, *, session: Session, normalized_url: str) -> ScrapeJob | None:
        return session.exec(
            select(ScrapeJob)
            .where(
                (col(ScrapeJob.normalized_url) == normalized_url)
                & (col(ScrapeJob.status) == "completed")
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
                started_at=scrape_job.started_at or scrape_job.created_at,
                finished_at=scrape_job.finished_at or scrape_job.updated_at,
            )
            session.add(crawl_job)
            session.flush()
        else:
            crawl_job.state = actual_state
            crawl_job.finished_at = scrape_job.finished_at or scrape_job.updated_at
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

    def _fail_job(
        self,
        *,
        engine: Any,
        analysis_job_id: UUID,
        error_code: str,
        error_message: str,
        lock_token: str,
        run_id: UUID,
        attempt_count: int,
        max_attempts: int,
    ) -> AnalysisJob:
        with Session(engine) as session:
            analysis_job = session.get(AnalysisJob, analysis_job_id)
            if analysis_job is None:
                raise RuntimeError(f"AnalysisJob {analysis_job_id} not found in _fail_job")

            # Re-verify ownership (guards against lock TTL expiry mid-run).
            if analysis_job.lock_token != lock_token:
                log_event(logger, "analysis_fail_skipped_not_owner", analysis_job_id=str(analysis_job_id))
                return analysis_job

            is_permanent = error_code in self._PERMANENT_ERROR_CODES
            attempts_exhausted = attempt_count >= max_attempts

            if is_permanent or attempts_exhausted:
                analysis_job.state = AnalysisJobState.DEAD if attempts_exhausted and not is_permanent else AnalysisJobState.FAILED
                analysis_job.terminal_state = True
                analysis_job.finished_at = utcnow()
            else:
                # Transient failure with retries remaining: put back to QUEUED and clear the
                # lock so the next worker can claim it immediately without waiting for TTL expiry.
                analysis_job.state = AnalysisJobState.QUEUED
                analysis_job.terminal_state = False
                analysis_job.lock_token = None
                analysis_job.lock_expires_at = None

            analysis_job.last_error_code = error_code
            analysis_job.last_error_message = error_message
            session.add(analysis_job)
            session.commit()
            if analysis_job.terminal_state:
                self._refresh_run_status(session=session, run_id=run_id)
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
