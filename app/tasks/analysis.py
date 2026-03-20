from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded  # type: ignore[import]
from sqlmodel import Session

from app.celery_app import app
from app.core.logging import log_event
from app.db.session import get_engine
from app.models import AnalysisJob
from app.models.pipeline import AnalysisJobState
from app.services.analysis_service import AnalysisService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@app.task(
    bind=True,
    name="app.tasks.analysis.run_analysis_job",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=1800,
    time_limit=1860,
    max_retries=3,
    queue="analysis",
)
def run_analysis_job(self, job_id: str) -> None:  # type: ignore[misc]
    """Celery task: run classification for a single AnalysisJob."""
    engine = get_engine()
    service = AnalysisService()
    try:
        result = service.run_analysis_job(engine=engine, analysis_job_id=UUID(job_id))
        if result is None:
            # CAS claim failed — another worker owns this job; nothing to do.
            log_event(logger, "analysis_task_skipped_not_owner", job_id=job_id)
            return
        if not result.terminal_state:
            # Transient failure — Celery will retry.
            log_event(logger, "analysis_task_retry", job_id=job_id, error_code=result.last_error_code)
            raise self.retry(countdown=30)
    except self.MaxRetriesExceededError:
        # All Celery retries exhausted — mark the job terminal so the Beat reconciler
        # doesn't pick it up again.
        log_event(logger, "analysis_task_max_retries_exceeded", job_id=job_id)
        with Session(engine) as session:
            job = session.get(AnalysisJob, UUID(job_id))
            if job and not job.terminal_state:
                job.state = AnalysisJobState.DEAD
                job.terminal_state = True
                job.last_error_code = "max_retries_exceeded"
                job.finished_at = _utcnow()
                session.add(job)
                session.commit()
        raise
    except SoftTimeLimitExceeded:
        log_event(logger, "analysis_task_timeout", job_id=job_id)
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "analysis_task_error", job_id=job_id, error=str(exc))
        raise
