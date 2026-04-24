from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models import Company, ContactRevealAttempt, ContactRevealJob
from app.models.pipeline import ContactFetchJobState, ContactProviderAttemptState, utcnow
from app.services.contact_runtime_service import ContactRuntimeService
from app.services.contact_service import ContactService, logger

__all__ = ["ContactRevealService"]


class ContactRevealService(ContactService):
    # ------------------------------------------------------------------
    # Reveal orchestration (S4)
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        self._runtime = ContactRuntimeService()

    def run_contact_reveal(self, *, engine: Any, job_id: UUID) -> ContactRevealJob | None:
        now = utcnow()
        lock_token = str(uuid4())
        try:
            with Session(engine) as session:
                job = self._claim_reveal_job(session=session, job_id=job_id, lock_token=lock_token, now=now)
                if job is None:
                    return None

                members = self._load_reveal_members(session=session, job=job)
                if not members:
                    return self._mark_reveal_job_failure(
                        engine=engine,
                        job_id=job_id,
                        lock_token=lock_token,
                        error_code="reveal_members_missing",
                        error_message="No discovered contacts found for reveal job.",
                    )

                requested_providers = [provider for provider in (job.requested_providers_json or []) if provider in {"apollo", "snov"}]
                self._ensure_reveal_attempts(session=session, job=job, requested_providers=requested_providers)
                attempts = list(
                    session.exec(
                        select(ContactRevealAttempt)
                        .where(col(ContactRevealAttempt.contact_reveal_job_id) == job.id)
                        .order_by(col(ContactRevealAttempt.sequence_index), col(ContactRevealAttempt.created_at))
                    )
                )
                running_attempt = any(
                    attempt.state == ContactProviderAttemptState.RUNNING and not attempt.terminal_state
                    for attempt in attempts
                )
                ready_attempts = [
                    attempt
                    for attempt in attempts
                    if (
                        not attempt.terminal_state
                        and attempt.state in {ContactProviderAttemptState.QUEUED, ContactProviderAttemptState.DEFERRED}
                        and (attempt.next_retry_at is None or attempt.next_retry_at <= now)
                    )
                ]
                waiting_retry = any(
                    not attempt.terminal_state
                    and attempt.state == ContactProviderAttemptState.DEFERRED
                    and attempt.next_retry_at is not None
                    and attempt.next_retry_at > now
                    for attempt in attempts
                )

                if ready_attempts:
                    self._release_reveal_job(session=session, job=job, state=ContactFetchJobState.RUNNING)
                    self._refresh_reveal_batch_state(session, batch_id=job.contact_reveal_batch_id)
                    session.commit()
                    session.refresh(job)
                    for attempt in ready_attempts[:1]:
                        self._dispatch_reveal_attempt(attempt=attempt)
                    return job

                if running_attempt or waiting_retry:
                    self._release_reveal_job(
                        session=session,
                        job=job,
                        state=ContactFetchJobState.RUNNING if running_attempt else ContactFetchJobState.QUEUED,
                    )
                    self._refresh_reveal_batch_state(session, batch_id=job.contact_reveal_batch_id)
                    session.commit()
                    session.refresh(job)
                    return job

                finalized_job = self._finalize_reveal_job(session=session, job=job)
                session.commit()
                session.refresh(finalized_job)
                return finalized_job
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "contact_reveal_job_unexpected_error", job_id=str(job_id), error=str(exc))
            return self._mark_reveal_job_failure(
                engine=engine,
                job_id=job_id,
                lock_token=lock_token,
                error_code="contact_reveal_job_unexpected",
                error_message=str(exc),
            )

    def run_contact_reveal_apollo_attempt(self, *, engine: Any, attempt_id: UUID) -> ContactRevealAttempt | None:
        return self._run_reveal_attempt(engine=engine, attempt_id=attempt_id, provider="apollo")

    def run_contact_reveal_snov_attempt(self, *, engine: Any, attempt_id: UUID) -> ContactRevealAttempt | None:
        return self._run_reveal_attempt(engine=engine, attempt_id=attempt_id, provider="snov")
