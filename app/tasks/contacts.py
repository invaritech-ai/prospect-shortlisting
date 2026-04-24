from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded  # type: ignore[import]
from sqlmodel import Session

from app.celery_app import app
from app.core.logging import log_event
from app.db.session import get_engine
from app.models import ContactVerifyJob
from app.models.pipeline import ContactVerifyJobState
from app.services.contact_queue_service import ContactQueueService
from app.services.contact_service import ContactService
from app.services.contact_reveal_service import ContactRevealService
from app.services.contact_verify_service import ContactVerifyService

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
    queue="contacts_orchestrator",
)
def fetch_contacts(self, job_id: str) -> None:  # type: ignore[misc]
    """Orchestrate a company-level contact fetch job."""
    engine = get_engine()
    service = ContactService()
    try:
        result = service.run_contact_fetch(engine=engine, job_id=UUID(job_id))
        if result is None:
            log_event(logger, "contact_task_skipped_not_owner", job_id=job_id)
            return
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_task_timeout", job_id=job_id)
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_task_error", job_id=job_id, error=str(exc))


@app.task(
    bind=True,
    name="app.tasks.contacts.fetch_contacts_apollo",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    queue="contacts_orchestrator",
)
def fetch_contacts_apollo(self, job_id: str) -> None:  # type: ignore[misc]
    """Legacy compatibility wrapper for Apollo-primary contact jobs."""
    engine = get_engine()
    service = ContactService()
    try:
        result = service.run_apollo_fetch(engine=engine, job_id=UUID(job_id))
        if result is None:
            log_event(logger, "contact_task_skipped_not_owner", job_id=job_id)
            return
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_task_timeout", job_id=job_id)
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_task_error", job_id=job_id, error=str(exc))


@app.task(
    bind=True,
    name="app.tasks.contacts.fetch_contacts_snov_attempt",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    queue="contacts_snov",
)
def fetch_contacts_snov_attempt(self, attempt_id: str) -> None:  # type: ignore[misc]
    """Execute one Snov provider attempt for a contact fetch job."""
    engine = get_engine()
    service = ContactService()
    try:
        service.run_snov_attempt(engine=engine, attempt_id=UUID(attempt_id))
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_provider_attempt_timeout", attempt_id=attempt_id, provider="snov")
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_provider_attempt_error", attempt_id=attempt_id, provider="snov", error=str(exc))


@app.task(
    bind=True,
    name="app.tasks.contacts.fetch_contacts_apollo_attempt",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    queue="contacts_apollo",
)
def fetch_contacts_apollo_attempt(self, attempt_id: str) -> None:  # type: ignore[misc]
    """Execute one Apollo provider attempt for a contact fetch job."""
    engine = get_engine()
    service = ContactService()
    try:
        service.run_apollo_attempt(engine=engine, attempt_id=UUID(attempt_id))
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_provider_attempt_timeout", attempt_id=attempt_id, provider="apollo")
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_provider_attempt_error", attempt_id=attempt_id, provider="apollo", error=str(exc))


@app.task(
    bind=True,
    name="app.tasks.contacts.reveal_contact_emails",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    queue="contacts_reveal_orchestrator",
)
def reveal_contact_emails(self, job_id: str) -> None:  # type: ignore[misc]
    engine = get_engine()
    service = ContactRevealService()
    try:
        result = service.run_contact_reveal(engine=engine, job_id=UUID(job_id))
        if result is None:
            log_event(logger, "contact_reveal_task_skipped_not_owner", job_id=job_id)
            return
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_reveal_task_timeout", job_id=job_id)
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_reveal_task_error", job_id=job_id, error=str(exc))


@app.task(
    bind=True,
    name="app.tasks.contacts.reveal_contact_apollo_attempt",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    queue="contacts_reveal_apollo",
)
def reveal_contact_apollo_attempt(self, attempt_id: str) -> None:  # type: ignore[misc]
    engine = get_engine()
    service = ContactRevealService()
    try:
        service.run_contact_reveal_apollo_attempt(engine=engine, attempt_id=UUID(attempt_id))
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_reveal_attempt_timeout", attempt_id=attempt_id, provider="apollo")
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_reveal_attempt_error", attempt_id=attempt_id, provider="apollo", error=str(exc))


@app.task(
    bind=True,
    name="app.tasks.contacts.reveal_contact_snov_attempt",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    queue="contacts_reveal_snov",
)
def reveal_contact_snov_attempt(self, attempt_id: str) -> None:  # type: ignore[misc]
    engine = get_engine()
    service = ContactRevealService()
    try:
        service.run_contact_reveal_snov_attempt(engine=engine, attempt_id=UUID(attempt_id))
    except SoftTimeLimitExceeded:
        log_event(logger, "contact_reveal_attempt_timeout", attempt_id=attempt_id, provider="snov")
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "contact_reveal_attempt_error", attempt_id=attempt_id, provider="snov", error=str(exc))


@app.task(
    name="app.tasks.contacts.dispatch_contact_fetch_jobs",
    queue="contacts_orchestrator",
)
def dispatch_contact_fetch_jobs() -> None:
    engine = get_engine()
    with Session(engine) as session:
        dispatched = ContactQueueService().dispatch_queued_jobs(session=session)
    log_event(logger, "contact_dispatcher_ran", dispatched=dispatched)


@app.task(
    bind=True,
    name="app.tasks.contacts.verify_contacts_batch",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
    max_retries=3,
    queue="contacts_verify",
)
def verify_contacts_batch(self, job_id: str) -> None:  # type: ignore[misc]
    """Celery task: run ZeroBounce verification for one ContactVerifyJob."""
    engine = get_engine()
    service = ContactVerifyService()
    try:
        result = service.run_verify_job(engine=engine, job_id=UUID(job_id))
        if result is None:
            log_event(logger, "verify_task_skipped_not_owner", job_id=job_id)
            return
        if not result.terminal_state:
            log_event(logger, "verify_task_retry", job_id=job_id, error_code=result.last_error_code)
            raise self.retry(countdown=30)
    except self.MaxRetriesExceededError:
        log_event(logger, "verify_task_max_retries_exceeded", job_id=job_id)
        with Session(engine) as session:
            job = session.get(ContactVerifyJob, UUID(job_id))
            if job and not job.terminal_state:
                job.state = ContactVerifyJobState.FAILED
                job.terminal_state = True
                job.last_error_code = "max_retries_exceeded"
                job.finished_at = _utcnow()
                session.add(job)
                session.commit()
        raise
    except SoftTimeLimitExceeded:
        log_event(logger, "verify_task_timeout", job_id=job_id)
        raise
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "verify_task_error", job_id=job_id, error=str(exc))
        raise
