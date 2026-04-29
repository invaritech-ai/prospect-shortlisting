from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.models import ContactVerifyJob, Contact
from app.models.pipeline import ContactVerifyJobState
from app.services.zerobounce_client import (
    ERR_ZEROBOUNCE_AUTH_FAILED,
    ERR_ZEROBOUNCE_KEY_MISSING,
    ZeroBounceClient,
)

_VERIFY_LOCK_TTL = timedelta(minutes=15)
_PERMANENT_ERROR_CODES = frozenset({ERR_ZEROBOUNCE_KEY_MISSING, ERR_ZEROBOUNCE_AUTH_FAILED})
_zerobounce = ZeroBounceClient()


def utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def normalize_zerobounce_status(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"catch-all", "catch_all"}:
        return "catch_all"
    if value in {"not_valid", "not valid"}:
        return "invalid"
    return value or "unknown"


def is_contact_verification_eligible(contact: Contact) -> bool:
    return (
        contact.title_match
        and bool((contact.email or "").strip())
        and (contact.verification_status or "unverified") == "unverified"
    )


class ContactVerifyService:
    def run_verify_job(self, *, engine: Any, job_id: UUID) -> ContactVerifyJob | None:
        now = utcnow()
        lock_token = str(uuid4())

        with Session(engine) as session:
            session.execute(
                sa_update(ContactVerifyJob)
                .where(
                    col(ContactVerifyJob.id) == job_id,
                    col(ContactVerifyJob.terminal_state).is_(False),
                    col(ContactVerifyJob.state).in_([
                        ContactVerifyJobState.QUEUED,
                        ContactVerifyJobState.RUNNING,
                    ]),
                    or_(
                        col(ContactVerifyJob.lock_token).is_(None),
                        col(ContactVerifyJob.lock_expires_at) < now,
                    ),
                )
                .values(
                    state=ContactVerifyJobState.RUNNING,
                    attempt_count=col(ContactVerifyJob.attempt_count) + 1,
                    lock_token=lock_token,
                    lock_expires_at=now + _VERIFY_LOCK_TTL,
                    last_error_code=None,
                    last_error_message=None,
                    updated_at=now,
                )
            )
            session.commit()

            job = session.get(ContactVerifyJob, job_id)
            if not job or job.lock_token != lock_token:
                return None

            if not job.started_at:
                job.started_at = now
                session.add(job)
                session.commit()

            requested_ids = [
                UUID(raw_id)
                for raw_id in (job.contact_ids_json or [])
                if isinstance(raw_id, str)
            ]
            attempt_count = job.attempt_count
            max_attempts = job.max_attempts

        with Session(engine) as session:
            contacts = list(
                session.exec(
                    select(Contact).where(col(Contact.id).in_(requested_ids))
                )
            ) if requested_ids else []

        if not contacts:
            return self._complete_job(
                engine=engine,
                job_id=job_id,
                lock_token=lock_token,
                verified_count=0,
                skipped_count=0,
            )

        eligible = [contact for contact in contacts if is_contact_verification_eligible(contact)]
        if not eligible:
            return self._complete_job(
                engine=engine,
                job_id=job_id,
                lock_token=lock_token,
                verified_count=0,
                skipped_count=len(contacts),
            )

        email_map: dict[str, list[UUID]] = {}
        for contact in eligible:
            email = (contact.email or "").strip().lower()
            if not email:
                continue
            email_map.setdefault(email, []).append(contact.id)

        results, err = _zerobounce.validate_batch(list(email_map))
        if err:
            return self._fail_job(
                engine=engine,
                job_id=job_id,
                lock_token=lock_token,
                error_code=err,
                error_message=f"ZeroBounce verification failed: {err}",
                attempt_count=attempt_count,
                max_attempts=max_attempts,
            )

        by_email = {
            str(item.get("address") or "").strip().lower(): item
            for item in results
            if str(item.get("address") or "").strip()
        }

        verified_count = 0
        skipped_count = len(contacts) - len(eligible)
        with Session(engine) as session:
            job = session.get(ContactVerifyJob, job_id)
            if not job or job.lock_token != lock_token:
                return None

            db_contacts = list(
                session.exec(
                    select(Contact).where(col(Contact.id).in_([c.id for c in eligible]))
                )
            )
            for contact in db_contacts:
                email = (contact.email or "").strip().lower()
                payload = by_email.get(email)
                if payload is None:
                    skipped_count += 1
                    continue
                contact.verification_status = normalize_zerobounce_status(str(payload.get("status") or "unknown"))
                contact.zerobounce_raw = payload
                has_email = bool((contact.email or "").strip())
                if has_email and contact.title_match and contact.verification_status == "valid":
                    contact.pipeline_stage = "campaign_ready"
                elif has_email:
                    contact.pipeline_stage = "email_revealed"
                else:
                    contact.pipeline_stage = "fetched"
                contact.updated_at = utcnow()
                session.add(contact)
                verified_count += 1

            session.commit()

        return self._complete_job(
            engine=engine,
            job_id=job_id,
            lock_token=lock_token,
            verified_count=verified_count,
            skipped_count=skipped_count,
        )

    def _complete_job(
        self,
        *,
        engine: Any,
        job_id: UUID,
        lock_token: str,
        verified_count: int,
        skipped_count: int,
    ) -> ContactVerifyJob | None:
        with Session(engine) as session:
            job = session.get(ContactVerifyJob, job_id)
            if not job or job.lock_token != lock_token:
                return None
            now = utcnow()
            job.state = ContactVerifyJobState.SUCCEEDED
            job.terminal_state = True
            job.verified_count = verified_count
            job.skipped_count = skipped_count
            job.finished_at = now
            job.updated_at = now
            job.lock_token = None
            job.lock_expires_at = None
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def _fail_job(
        self,
        *,
        engine: Any,
        job_id: UUID,
        lock_token: str,
        error_code: str,
        error_message: str,
        attempt_count: int,
        max_attempts: int,
    ) -> ContactVerifyJob | None:
        with Session(engine) as session:
            job = session.get(ContactVerifyJob, job_id)
            if not job or job.lock_token != lock_token:
                return None

            is_terminal = error_code in _PERMANENT_ERROR_CODES or attempt_count >= max_attempts
            job.state = ContactVerifyJobState.FAILED if is_terminal else ContactVerifyJobState.QUEUED
            job.terminal_state = is_terminal
            job.last_error_code = error_code
            job.last_error_message = error_message
            job.updated_at = utcnow()
            job.lock_token = None
            job.lock_expires_at = None
            if is_terminal:
                job.finished_at = utcnow()
            session.add(job)
            session.commit()
            session.refresh(job)
            return job
