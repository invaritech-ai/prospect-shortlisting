from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded  # type: ignore[import]
from sqlmodel import Session

from app.celery_app import app
from app.core.logging import log_event
from app.db.session import get_engine
from app.models import ContactFetchJob
from app.models.pipeline import ContactFetchJobState
from app.services.contact_service import ContactService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@app.task(
    bind=True,
    name="app.tasks.contacts.fetch_contacts",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    max_retries=3,
    queue="contacts",
)
def fetch_contacts(self, job_id: str) -> None:  # type: ignore[misc]
    """Celery task: fetch Snov.io contacts for a single ContactFetchJob."""
    engine = get_engine()
    service = ContactService()
    try:
        result = service.run_contact_fetch(engine=engine, job_id=UUID(job_id))
        if result is None:
            # CAS claim failed — another worker owns this job.
            log_event(logger, "contact_task_skipped_not_owner", job_id=job_id)
            return
        if not result.terminal_state:
            # Transient failure — retry via Celery.
            log_event(logger, "contact_task_retry", job_id=job_id, error_code=result.last_error_code)
            raise self.retry(countdown=30)
    except self.MaxRetriesExceededError:
        log_event(logger, "contact_task_max_retries_exceeded", job_id=job_id)
        with Session(engine) as session:
            job = session.get(ContactFetchJob, UUID(job_id))
            if job and not job.terminal_state:
                job.state = ContactFetchJobState.DEAD
                job.terminal_state = True
                job.last_error_code = "max_retries_exceeded"
                job.finished_at = _utcnow()
                session.add(job)
                session.commit()
        raise
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_task_timeout", job_id=job_id)
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_task_error", job_id=job_id, error=str(exc))
        raise
