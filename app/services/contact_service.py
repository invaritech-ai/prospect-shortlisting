from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models import (
    Company,
    ContactFetchJob,
    ContactProviderAttempt,
    DiscoveredContact,
    Upload,
)
from app.models.pipeline import (
    ContactFetchJobState,
    ContactProviderAttemptState,
    utcnow,
)
from app.services.apollo_client import (
    ERR_APOLLO_AUTH_FAILED,
    ERR_APOLLO_CREDENTIALS_MISSING,
    ApolloClient,
)
from app.services.contact_queue_service import DISCOVERY_PROVIDER_ORDER, ContactQueueService
from app.services.contact_runtime_service import ContactRuntimeService
from app.services.snov_client import (
    ERR_SNOV_AUTH_FAILED,
    ERR_SNOV_CREDENTIALS_MISSING,
    SnovClient,
)
from app.services.title_match_service import (
    compute_title_rule_stats,
    load_title_rules,
    match_title,
    rematch_discovered_contacts,
    seed_title_rules,
    test_title_match_detailed,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ContactService",
    "compute_title_rule_stats",
    "load_title_rules",
    "match_title",
    "rematch_discovered_contacts",
    "seed_title_rules",
    "test_title_match_detailed",
]

_CONTACT_LOCK_TTL = timedelta(minutes=15)

_PERMANENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        ERR_SNOV_CREDENTIALS_MISSING,
        ERR_SNOV_AUTH_FAILED,
        ERR_APOLLO_CREDENTIALS_MISSING,
        ERR_APOLLO_AUTH_FAILED,
    }
)

_snov = SnovClient()
_apollo = ApolloClient()


def _provider_native_person_id(provider: str, payload: dict[str, Any]) -> str:
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider == "apollo":
        return str(payload.get("id") or "").strip()
    if normalized_provider == "snov":
        for key in ("id", "user_id", "search_emails_start"):
            provider_id = str(payload.get(key) or "").strip()
            if provider_id:
                return provider_id
    return ""



def _company_campaign_id(session: Session, *, company_id: UUID) -> UUID | None:
    return session.exec(
        select(Upload.campaign_id)
        .join(Company, col(Company.upload_id) == col(Upload.id))
        .where(col(Company.id) == company_id)
    ).first()


@dataclass(frozen=True)
class DiscoveryProviderFetchResult:
    contacts: list[dict[str, Any]]
    title_matched_count: int
    error_code: str = ""
    error_message: str = ""


class ContactService:
    def __init__(self) -> None:
        self._runtime = ContactRuntimeService()
        self._queue = ContactQueueService()

    # ------------------------------------------------------------------
    # Discovery orchestration (S3)
    # ------------------------------------------------------------------

    def run_contact_fetch(self, *, engine: Any, job_id: UUID) -> ContactFetchJob | None:
        return self._run_contact_job(engine=engine, job_id=job_id, legacy_provider="snov")

    def run_apollo_fetch(self, *, engine: Any, job_id: UUID) -> ContactFetchJob | None:
        return self._run_contact_job(engine=engine, job_id=job_id, legacy_provider="apollo")

    def run_snov_attempt(self, *, engine: Any, attempt_id: UUID) -> ContactProviderAttempt | None:
        return self._run_provider_attempt(engine=engine, attempt_id=attempt_id, provider="snov")

    def run_apollo_attempt(self, *, engine: Any, attempt_id: UUID) -> ContactProviderAttempt | None:
        return self._run_provider_attempt(engine=engine, attempt_id=attempt_id, provider="apollo")

    def _run_contact_job(self, *, engine: Any, job_id: UUID, legacy_provider: str) -> ContactFetchJob | None:
        now = utcnow()
        lock_token = str(uuid4())
        try:
            with Session(engine) as session:
                job = self._claim_contact_job(session=session, job_id=job_id, lock_token=lock_token, now=now)
                if job is None:
                    log_event(logger, "contact_fetch_skipped_not_owner", job_id=str(job_id))
                    return None

                company = session.get(Company, job.company_id)
                if company is None:
                    return self._mark_job_failure(
                        engine=engine,
                        job_id=job_id,
                        lock_token=lock_token,
                        error_code="contact_company_missing",
                        error_message="Company not found.",
                    )

                requested_providers = self._requested_providers(job=job, legacy_provider=legacy_provider)
                if job.requested_providers_json != requested_providers:
                    job.requested_providers_json = requested_providers
                if requested_providers and job.provider != requested_providers[0]:
                    job.provider = requested_providers[0]
                self._ensure_provider_attempts(session=session, job=job, requested_providers=requested_providers)

                attempts = list(
                    session.exec(
                        select(ContactProviderAttempt)
                        .where(col(ContactProviderAttempt.contact_fetch_job_id) == job.id)
                        .order_by(col(ContactProviderAttempt.sequence_index), col(ContactProviderAttempt.created_at))
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
                    self._release_contact_job(
                        session=session,
                        job=job,
                        state=ContactFetchJobState.RUNNING,
                        error_code=None,
                        error_message=None,
                    )
                    self._queue.refresh_batch_state(session, batch_id=job.contact_fetch_batch_id)
                    session.commit()
                    session.refresh(job)
                    for attempt in ready_attempts:
                        self._dispatch_provider_attempt(attempt=attempt)
                    return job

                if running_attempt or waiting_retry:
                    self._release_contact_job(
                        session=session,
                        job=job,
                        state=ContactFetchJobState.RUNNING if running_attempt else ContactFetchJobState.QUEUED,
                        error_code=None,
                        error_message=None,
                    )
                    self._queue.refresh_batch_state(session, batch_id=job.contact_fetch_batch_id)
                    session.commit()
                    session.refresh(job)
                    return job

                finalized_job = self._finalize_contact_job(engine=engine, session=session, job=job)
                session.commit()
                session.refresh(finalized_job)
                return finalized_job
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "contact_job_unexpected_error", job_id=str(job_id), error=str(exc))
            return self._mark_job_failure(
                engine=engine,
                job_id=job_id,
                lock_token=lock_token,
                error_code="contact_job_unexpected",
                error_message=str(exc),
            )

    def _run_provider_attempt(self, *, engine: Any, attempt_id: UUID, provider: str) -> ContactProviderAttempt | None:
        now = utcnow()
        lock_token = str(uuid4())
        try:
            with Session(engine) as session:
                attempt = self._claim_provider_attempt(
                    session=session,
                    attempt_id=attempt_id,
                    provider=provider,
                    lock_token=lock_token,
                    now=now,
                )
                if attempt is None:
                    return None

                job = session.get(ContactFetchJob, attempt.contact_fetch_job_id)
                if job is None:
                    return self._fail_provider_attempt(
                        engine=engine,
                        attempt_id=attempt_id,
                        lock_token=lock_token,
                        error_code="contact_job_missing",
                        error_message="Parent contact fetch job not found.",
                    )
                company = session.get(Company, job.company_id)
                if company is None:
                    return self._fail_provider_attempt(
                        engine=engine,
                        attempt_id=attempt_id,
                        lock_token=lock_token,
                        error_code="contact_company_missing",
                        error_message="Company not found.",
                    )
                campaign_id = _company_campaign_id(session, company_id=company.id)
                include_rules, exclude_words = load_title_rules(session, campaign_id=campaign_id)

            decision = self._runtime.claim_provider_slot(provider)
            if decision.wait_seconds > 0:
                return self._defer_provider_attempt(
                    engine=engine,
                    attempt_id=attempt_id,
                    lock_token=lock_token,
                    error_code=f"{provider}_backpressure",
                    error_message=decision.reason or "Provider is throttled.",
                    deferred_reason=decision.reason or "provider_backpressure",
                    delay_seconds=decision.wait_seconds,
                )

            if provider == "apollo":
                result = self._fetch_apollo_contacts(
                    domain=company.domain,
                    include_rules=include_rules,
                    exclude_words=exclude_words,
                )
            else:
                result = self._fetch_snov_contacts(
                    domain=company.domain,
                    include_rules=include_rules,
                    exclude_words=exclude_words,
                )

            if result.error_code:
                if result.error_code in _PERMANENT_ERROR_CODES:
                    return self._fail_provider_attempt(
                        engine=engine,
                        attempt_id=attempt_id,
                        lock_token=lock_token,
                        error_code=result.error_code,
                        error_message=result.error_message,
                    )
                delay_seconds = self._runtime.record_provider_error(provider, result.error_code)
                return self._defer_provider_attempt(
                    engine=engine,
                    attempt_id=attempt_id,
                    lock_token=lock_token,
                    error_code=result.error_code,
                    error_message=result.error_message,
                    deferred_reason=result.error_code,
                    delay_seconds=delay_seconds,
                )

            self._runtime.record_provider_success(provider)
            contacts_written = self._persist_discovered_contacts(
                engine=engine,
                job_id=job.id,
                company_id=company.id,
                provider=provider,
                contacts_to_write=result.contacts,
            )
            return self._complete_provider_attempt(
                engine=engine,
                attempt_id=attempt_id,
                lock_token=lock_token,
                contacts_found=contacts_written,
                title_matched_count=result.title_matched_count,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "contact_provider_attempt_unexpected_error", attempt_id=str(attempt_id), error=str(exc))
            delay_seconds = self._runtime.record_provider_error(provider, "provider_unexpected")
            return self._defer_provider_attempt(
                engine=engine,
                attempt_id=attempt_id,
                lock_token=lock_token,
                error_code="provider_unexpected",
                error_message=str(exc),
                deferred_reason="provider_unexpected",
                delay_seconds=delay_seconds,
            )

    # ------------------------------------------------------------------
    # Discovery persistence and provider calls
    # ------------------------------------------------------------------

    def _fetch_apollo_contacts(
        self,
        *,
        domain: str,
        include_rules: list[list[str]],
        exclude_words: list[str],
    ) -> DiscoveryProviderFetchResult:
        all_prospects: list[dict[str, Any]] = []
        for page in range(1, 4):
            prospects = _apollo.search_people(domain, page=page, person_titles=None)
            if not prospects:
                if _apollo.last_error_code:
                    return DiscoveryProviderFetchResult(
                        contacts=[],
                        title_matched_count=0,
                        error_code=_apollo.last_error_code,
                        error_message=f"Apollo search failed: {_apollo.last_error_code}",
                    )
                break
            all_prospects.extend(prospects)
            if len(prospects) < 100:
                break

        contacts_to_write: list[dict[str, Any]] = []
        title_matched_count = 0
        for prospect in all_prospects:
            title = str(prospect.get("title") or prospect.get("position") or "").strip()
            title_matched = match_title(title, include_rules, exclude_words) if include_rules else False
            if title_matched:
                title_matched_count += 1
            contacts_to_write.append(
                {
                    "provider_person_id": _provider_native_person_id("apollo", prospect),
                    "first_name": str(prospect.get("first_name") or "").strip(),
                    "last_name": str(prospect.get("last_name") or prospect.get("last_name_obfuscated") or "").strip(),
                    "title": title or None,
                    "title_match": title_matched,
                    "linkedin_url": str(prospect.get("linkedin_url") or "").strip() or None,
                    "source_url": str(prospect.get("website_url") or prospect.get("photo_url") or "").strip() or None,
                    "provider_has_email": bool(prospect.get("has_email")) if prospect.get("has_email") is not None else None,
                    "provider_metadata_json": {
                        "has_email": prospect.get("has_email"),
                        "organization_id": prospect.get("organization_id"),
                    },
                    "raw_payload_json": prospect,
                }
            )
        return DiscoveryProviderFetchResult(
            contacts=contacts_to_write,
            title_matched_count=title_matched_count,
        )

    def _fetch_snov_contacts(
        self,
        *,
        domain: str,
        include_rules: list[list[str]],
        exclude_words: list[str],
    ) -> DiscoveryProviderFetchResult:
        all_prospects: list[dict[str, Any]] = []
        for page in range(1, 4):
            prospects, total, error_code = _snov.search_prospects(domain, page=page)
            if error_code:
                return DiscoveryProviderFetchResult(
                    contacts=[],
                    title_matched_count=0,
                    error_code=error_code,
                    error_message=f"Snov prospects failed: {error_code}",
                )
            all_prospects.extend(prospects)
            if len(all_prospects) >= total or len(prospects) == 0:
                break

        contacts_to_write: list[dict[str, Any]] = []
        title_matched_count = 0
        for prospect in all_prospects:
            title = str(prospect.get("position") or "").strip()
            title_matched = match_title(title, include_rules, exclude_words) if include_rules else False
            if title_matched:
                title_matched_count += 1
            contacts_to_write.append(
                {
                    "provider_person_id": _provider_native_person_id("snov", prospect),
                    "first_name": str(prospect.get("first_name") or "").strip(),
                    "last_name": str(prospect.get("last_name") or "").strip(),
                    "title": title or None,
                    "title_match": title_matched,
                    "linkedin_url": str(prospect.get("linkedin_url") or "").strip() or None,
                    "source_url": str(prospect.get("source_page") or "").strip() or None,
                    "provider_has_email": None,
                    "provider_metadata_json": {
                        "search_emails_start": prospect.get("search_emails_start"),
                    },
                    "raw_payload_json": prospect,
                }
            )
        return DiscoveryProviderFetchResult(
            contacts=contacts_to_write,
            title_matched_count=title_matched_count,
        )

    def _persist_discovered_contacts(
        self,
        *,
        engine: Any,
        job_id: UUID,
        company_id: UUID,
        provider: str,
        contacts_to_write: list[dict[str, Any]],
    ) -> int:
        with Session(engine) as session:
            existing_by_id = {
                contact.provider_person_id: contact
                for contact in session.exec(
                    select(DiscoveredContact).where(
                        col(DiscoveredContact.company_id) == company_id,
                        col(DiscoveredContact.provider) == provider,
                    )
                )
            }
            seen_ids: set[str] = set()
            now = utcnow()
            deduped: dict[str, dict[str, Any]] = {}
            for entry in contacts_to_write:
                provider_person_id = str(entry.get("provider_person_id") or "").strip()
                if not provider_person_id:
                    continue
                deduped[provider_person_id] = entry
            for provider_person_id, entry in deduped.items():
                seen_ids.add(provider_person_id)
                existing = existing_by_id.get(provider_person_id)
                if existing is None:
                    session.add(
                        DiscoveredContact(
                            company_id=company_id,
                            contact_fetch_job_id=job_id,
                            provider=provider,
                            provider_person_id=provider_person_id,
                            first_name=entry.get("first_name") or "",
                            last_name=entry.get("last_name") or "",
                            title=entry.get("title"),
                            title_match=bool(entry.get("title_match")),
                            linkedin_url=entry.get("linkedin_url"),
                            source_url=entry.get("source_url"),
                            provider_has_email=entry.get("provider_has_email"),
                            provider_metadata_json=entry.get("provider_metadata_json"),
                            raw_payload_json=entry.get("raw_payload_json"),
                            is_active=True,
                            backfilled=False,
                            discovered_at=now,
                            last_seen_at=now,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    continue
                existing.contact_fetch_job_id = job_id
                existing.first_name = entry.get("first_name") or existing.first_name
                existing.last_name = entry.get("last_name") or existing.last_name
                existing.title = entry.get("title") or existing.title
                existing.title_match = bool(entry.get("title_match"))
                existing.linkedin_url = entry.get("linkedin_url") or existing.linkedin_url
                existing.source_url = entry.get("source_url") or existing.source_url
                existing.provider_has_email = entry.get("provider_has_email")
                existing.provider_metadata_json = entry.get("provider_metadata_json")
                existing.raw_payload_json = entry.get("raw_payload_json")
                existing.is_active = True
                existing.last_seen_at = now
                existing.updated_at = now
                session.add(existing)

            for existing in existing_by_id.values():
                if existing.provider_person_id in seen_ids:
                    continue
                if not existing.is_active:
                    continue
                existing.is_active = False
                existing.updated_at = now
                session.add(existing)
            session.commit()
        return len(deduped)

    # ------------------------------------------------------------------
    # Shared job state helpers
    # ------------------------------------------------------------------

    def _requested_providers(self, *, job: ContactFetchJob, legacy_provider: str) -> list[str]:
        allowed = set(DISCOVERY_PROVIDER_ORDER)
        requested_set = {
            str(provider).strip().lower()
            for provider in (job.requested_providers_json or [])
            if str(provider).strip().lower() in allowed
        }
        requested = [provider for provider in DISCOVERY_PROVIDER_ORDER if provider in requested_set]
        if requested:
            return requested
        primary = str(getattr(job, "provider", legacy_provider) or legacy_provider).strip().lower()
        next_provider = str(getattr(job, "next_provider", "") or "").strip().lower()
        requested = []
        if primary in allowed:
            requested.append(primary)
        if next_provider in allowed and next_provider not in requested:
            requested.append(next_provider)
        if not requested:
            requested.append(legacy_provider)
        return requested

    def _claim_contact_job(
        self,
        *,
        session: Session,
        job_id: UUID,
        lock_token: str,
        now: datetime,
    ) -> ContactFetchJob | None:
        session.execute(
            sa_update(ContactFetchJob)
            .where(
                col(ContactFetchJob.id) == job_id,
                col(ContactFetchJob.terminal_state).is_(False),
                col(ContactFetchJob.state).in_([ContactFetchJobState.QUEUED, ContactFetchJobState.RUNNING]),
                or_(
                    col(ContactFetchJob.lock_token).is_(None),
                    col(ContactFetchJob.lock_expires_at) < now,
                ),
            )
            .values(
                state=ContactFetchJobState.RUNNING,
                attempt_count=col(ContactFetchJob.attempt_count) + 1,
                lock_token=lock_token,
                lock_expires_at=now + _CONTACT_LOCK_TTL,
                last_error_code=None,
                last_error_message=None,
                updated_at=now,
            )
        )
        session.commit()
        job = session.get(ContactFetchJob, job_id)
        if job is None or job.lock_token != lock_token:
            return None
        if not job.started_at:
            job.started_at = now
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    def _ensure_provider_attempts(
        self,
        *,
        session: Session,
        job: ContactFetchJob,
        requested_providers: list[str],
    ) -> None:
        existing = {
            attempt.provider: attempt
            for attempt in session.exec(
                select(ContactProviderAttempt).where(
                    col(ContactProviderAttempt.contact_fetch_job_id) == job.id
                )
            )
        }
        for index, provider in enumerate(requested_providers):
            if provider in existing:
                continue
            session.add(
                ContactProviderAttempt(
                    contact_fetch_job_id=job.id,
                    provider=provider,
                    sequence_index=index,
                    max_attempts=max(5, job.max_attempts),
                )
            )
        session.commit()

    def _claim_provider_attempt(
        self,
        *,
        session: Session,
        attempt_id: UUID,
        provider: str,
        lock_token: str,
        now: datetime,
    ) -> ContactProviderAttempt | None:
        session.execute(
            sa_update(ContactProviderAttempt)
            .where(
                col(ContactProviderAttempt.id) == attempt_id,
                col(ContactProviderAttempt.provider) == provider,
                col(ContactProviderAttempt.terminal_state).is_(False),
                col(ContactProviderAttempt.state).in_(
                    [
                        ContactProviderAttemptState.QUEUED,
                        ContactProviderAttemptState.DEFERRED,
                        ContactProviderAttemptState.RUNNING,
                    ]
                ),
                or_(
                    col(ContactProviderAttempt.lock_token).is_(None),
                    col(ContactProviderAttempt.lock_expires_at) < now,
                ),
            )
            .values(
                state=ContactProviderAttemptState.RUNNING,
                attempt_count=col(ContactProviderAttempt.attempt_count) + 1,
                lock_token=lock_token,
                lock_expires_at=now + _CONTACT_LOCK_TTL,
                deferred_reason=None,
                next_retry_at=None,
                last_error_code=None,
                last_error_message=None,
                updated_at=now,
            )
        )
        session.commit()
        attempt = session.get(ContactProviderAttempt, attempt_id)
        if attempt is None or attempt.lock_token != lock_token:
            return None
        if not attempt.started_at:
            attempt.started_at = now
            session.add(attempt)
            session.commit()
            session.refresh(attempt)
        return attempt

    def _release_contact_job(
        self,
        *,
        session: Session,
        job: ContactFetchJob,
        state: ContactFetchJobState,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        job.state = state
        job.terminal_state = False
        job.lock_token = None
        job.lock_expires_at = None
        job.last_error_code = error_code
        job.last_error_message = error_message
        job.updated_at = utcnow()
        session.add(job)

    def _finalize_contact_job(
        self,
        *,
        engine: Any,
        session: Session,
        job: ContactFetchJob,
    ) -> ContactFetchJob:
        attempts = list(
            session.exec(
                select(ContactProviderAttempt).where(
                    col(ContactProviderAttempt.contact_fetch_job_id) == job.id
                )
            )
        )
        contacts_found = sum(int(attempt.contacts_found or 0) for attempt in attempts)
        title_matched_count = sum(int(attempt.title_matched_count or 0) for attempt in attempts)
        first_error = next(
            (
                (attempt.last_error_code, attempt.last_error_message)
                for attempt in attempts
                if attempt.last_error_code
            ),
            (None, None),
        )
        if attempts and all(attempt.terminal_state for attempt in attempts):
            if any(attempt.state == ContactProviderAttemptState.DEAD for attempt in attempts):
                job.state = ContactFetchJobState.DEAD
                job.last_error_code = first_error[0]
                job.last_error_message = first_error[1]
            elif any(attempt.state == ContactProviderAttemptState.FAILED for attempt in attempts):
                job.state = ContactFetchJobState.FAILED
                job.last_error_code = first_error[0]
                job.last_error_message = first_error[1]
            else:
                job.state = ContactFetchJobState.SUCCEEDED
                job.last_error_code = None
                job.last_error_message = None
        else:
            job.state = ContactFetchJobState.SUCCEEDED
            job.last_error_code = None
            job.last_error_message = None
        job.terminal_state = True
        job.contacts_found = contacts_found
        job.title_matched_count = title_matched_count
        job.finished_at = utcnow()
        job.updated_at = utcnow()
        job.lock_token = None
        job.lock_expires_at = None
        session.add(job)
        # Reveal is campaign-triggered; no auto-enqueue.
        self._queue.refresh_batch_state(session, batch_id=job.contact_fetch_batch_id)
        return job

    def _mark_job_failure(
        self,
        *,
        engine: Any,
        job_id: UUID,
        lock_token: str,
        error_code: str,
        error_message: str,
    ) -> ContactFetchJob | None:
        with Session(engine) as session:
            job = session.get(ContactFetchJob, job_id)
            if job is None or job.lock_token != lock_token:
                return job
            if job.attempt_count >= job.max_attempts or error_code in _PERMANENT_ERROR_CODES:
                job.state = ContactFetchJobState.FAILED if error_code in _PERMANENT_ERROR_CODES else ContactFetchJobState.DEAD
                job.terminal_state = True
                job.finished_at = utcnow()
            else:
                job.state = ContactFetchJobState.QUEUED
                job.terminal_state = False
            job.lock_token = None
            job.lock_expires_at = None
            job.last_error_code = error_code
            job.last_error_message = error_message[:4000]
            job.updated_at = utcnow()
            session.add(job)
            self._queue.refresh_batch_state(session, batch_id=job.contact_fetch_batch_id)
            session.commit()
            session.refresh(job)
            return job

    def _complete_provider_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        lock_token: str,
        contacts_found: int,
        title_matched_count: int,
    ) -> ContactProviderAttempt | None:
        dispatch_job_id: UUID | None = None
        dispatch_provider: str | None = None
        with Session(engine) as session:
            attempt = session.get(ContactProviderAttempt, attempt_id)
            if attempt is None or attempt.lock_token != lock_token:
                return attempt
            attempt.state = ContactProviderAttemptState.SUCCEEDED
            attempt.terminal_state = True
            attempt.contacts_found = contacts_found
            attempt.title_matched_count = title_matched_count
            attempt.deferred_reason = None
            attempt.next_retry_at = None
            attempt.last_error_code = None
            attempt.last_error_message = None
            attempt.lock_token = None
            attempt.lock_expires_at = None
            attempt.finished_at = utcnow()
            attempt.updated_at = utcnow()
            session.add(attempt)
            job = session.get(ContactFetchJob, attempt.contact_fetch_job_id)
            if job is not None:
                dispatch_job_id = job.id
                dispatch_provider = job.provider
            session.commit()
            session.refresh(attempt)
        if dispatch_job_id and dispatch_provider:
            self._dispatch_contact_task(provider=dispatch_provider, job_id=dispatch_job_id)
        return attempt

    def _defer_provider_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        lock_token: str,
        error_code: str,
        error_message: str,
        deferred_reason: str,
        delay_seconds: int,
    ) -> ContactProviderAttempt | None:
        dispatch_job_id: UUID | None = None
        dispatch_provider: str | None = None
        with Session(engine) as session:
            attempt = session.get(ContactProviderAttempt, attempt_id)
            if attempt is None or attempt.lock_token != lock_token:
                return attempt
            if attempt.attempt_count >= attempt.max_attempts:
                attempt.state = ContactProviderAttemptState.DEAD
                attempt.terminal_state = True
                attempt.finished_at = utcnow()
            else:
                attempt.state = ContactProviderAttemptState.DEFERRED
                attempt.terminal_state = False
                attempt.next_retry_at = utcnow() + timedelta(seconds=max(1, delay_seconds))
            attempt.deferred_reason = deferred_reason
            attempt.last_error_code = error_code
            attempt.last_error_message = error_message[:4000]
            attempt.lock_token = None
            attempt.lock_expires_at = None
            attempt.updated_at = utcnow()
            session.add(attempt)
            job = session.get(ContactFetchJob, attempt.contact_fetch_job_id)
            if job is not None:
                dispatch_job_id = job.id
                dispatch_provider = job.provider
            session.commit()
            session.refresh(attempt)
        if dispatch_job_id and dispatch_provider:
            self._dispatch_contact_task(provider=dispatch_provider, job_id=dispatch_job_id)
        return attempt

    def _fail_provider_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        lock_token: str,
        error_code: str,
        error_message: str,
    ) -> ContactProviderAttempt | None:
        dispatch_job_id: UUID | None = None
        dispatch_provider: str | None = None
        with Session(engine) as session:
            attempt = session.get(ContactProviderAttempt, attempt_id)
            if attempt is None or attempt.lock_token != lock_token:
                return attempt
            attempt.state = ContactProviderAttemptState.FAILED if error_code in _PERMANENT_ERROR_CODES else ContactProviderAttemptState.DEAD
            attempt.terminal_state = True
            attempt.deferred_reason = None
            attempt.next_retry_at = None
            attempt.last_error_code = error_code
            attempt.last_error_message = error_message[:4000]
            attempt.lock_token = None
            attempt.lock_expires_at = None
            attempt.finished_at = utcnow()
            attempt.updated_at = utcnow()
            session.add(attempt)
            job = session.get(ContactFetchJob, attempt.contact_fetch_job_id)
            if job is not None:
                dispatch_job_id = job.id
                dispatch_provider = job.provider
            session.commit()
            session.refresh(attempt)
        if dispatch_job_id and dispatch_provider:
            self._dispatch_contact_task(provider=dispatch_provider, job_id=dispatch_job_id)
        return attempt


    # ------------------------------------------------------------------
    # Task dispatch
    # ------------------------------------------------------------------

    def _dispatch_contact_task(self, *, provider: str, job_id: UUID) -> None:
        from app.tasks.contacts import fetch_contacts, fetch_contacts_apollo

        if provider == "apollo":
            fetch_contacts_apollo.delay(str(job_id))
        else:
            fetch_contacts.delay(str(job_id))

    def _dispatch_provider_attempt(self, *, attempt: ContactProviderAttempt) -> None:
        from app.tasks.contacts import fetch_contacts_apollo_attempt, fetch_contacts_snov_attempt

        if attempt.provider == "apollo":
            fetch_contacts_apollo_attempt.delay(str(attempt.id))
        else:
            fetch_contacts_snov_attempt.delay(str(attempt.id))

