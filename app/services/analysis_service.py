"""AnalysisJob execution: CAS-claim, LLM call, write ClassificationResult."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models import (
    AnalysisJob,
    ClassificationResult,
    Company,
    Prompt,
    Run,
)
from app.models.pipeline import AnalysisJobState, PredictedLabel
from app.services.context_service import (
    analysis_pages_for_job,
    build_context,
    latest_completed_scrape_job,
    render_prompt,
)
from app.services.llm_client import ERR_API_KEY_MISSING, ERR_RATE_LIMITED, LLMClient
from app.services.run_service import RunService


logger = logging.getLogger(__name__)

_analysis_llm = LLMClient(purpose="analysis", min_interval_sec=0.5)

# Re-export for code that imports these from analysis_service directly.
from app.services.context_service import ANALYSIS_PAGE_ORDER, MAX_CHARS_PER_PAGE, MAX_TOTAL_CONTEXT_CHARS  # noqa: E402, F401


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
    # Error codes that are permanent — skip all Celery retries.
    _PERMANENT_ERROR_CODES: frozenset[str] = frozenset({
        "analysis_dependencies_missing",
        "analysis_api_key_missing",
        "analysis_llm_rate_limited",
        "scrape_missing",
        "analysis_context_empty",
    })

    _LLM_ERROR_MAP: dict[str, str] = {
        ERR_API_KEY_MISSING: "analysis_api_key_missing",
        ERR_RATE_LIMITED:    "analysis_llm_rate_limited",
    }

    def __init__(self) -> None:
        self._run_service = RunService()

    # ── Delegate create_runs to RunService (kept for backwards compat) ───────
    def create_runs(self, **kwargs):  # type: ignore[override]
        return self._run_service.create_runs(**kwargs)

    def run_analysis_job(self, *, engine: Any, analysis_job_id: UUID) -> AnalysisJob | None:
        """Run classification for a single AnalysisJob.

        Uses two short-lived DB sessions so the connection is not held open
        during the (potentially long) LLM call.
        """
        _ANALYSIS_LOCK_TTL = timedelta(minutes=35)

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
                self._run_service.refresh_run_status(session=session, run_id=analysis_job.run_id)
                return analysis_job

            latest_scrape = latest_completed_scrape_job(session=session, normalized_url=company.normalized_url)

            run_id = run.id
            attempt_count = analysis_job.attempt_count
            max_attempts = analysis_job.max_attempts
            early_fail: tuple[str, str] | None = None

            if latest_scrape is None:
                early_fail = ("scrape_missing", "No completed scrape job found for company.")
                classify_model = ""
                rendered_prompt = ""
            else:
                pages = analysis_pages_for_job(session=session, job_id=latest_scrape.id)
                context = build_context(pages)
                if not context:
                    early_fail = ("analysis_context_empty", "No markdown content found for analysis.")
                    classify_model = ""
                    rendered_prompt = ""
                else:
                    classify_model = run.classify_model
                    rendered_prompt = render_prompt(
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
            self._run_service.refresh_run_status(session=session, run_id=run_id)
            session.refresh(analysis_job)
            return analysis_job

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
                analysis_job.state = AnalysisJobState.QUEUED
                analysis_job.terminal_state = False
                analysis_job.lock_token = None
                analysis_job.lock_expires_at = None

            analysis_job.last_error_code = error_code
            analysis_job.last_error_message = error_message
            session.add(analysis_job)
            session.commit()
            if analysis_job.terminal_state:
                self._run_service.refresh_run_status(session=session, run_id=run_id)
            session.refresh(analysis_job)
            return analysis_job
