from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models import (
    Company,
    ContactFetchJob,
    ContactProviderAttempt,
    ContactRevealAttempt,
    ContactRevealBatch,
    ContactRevealJob,
    DiscoveredContact,
    ProspectContact,
    ProspectContactEmail,
    Upload,
)
from app.models.pipeline import (
    ContactFetchBatchState,
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
from app.services.pipeline_service import recompute_contact_stages
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


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _normalize_name(value: str | None) -> str:
    return (value or "").strip().lower()


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


def enqueue_s4_for_contact_success(*, engine: Any, contact_fetch_job_id: UUID) -> None:
    """Compatibility hook for the S4 reveal enqueue boundary.

    The fetch pipeline still signals successful S3 completion through this
    callback so tests and downstream orchestration can observe the transition.
    """


def _company_campaign_id(session: Session, *, company_id: UUID) -> UUID | None:
    return session.exec(
        select(Upload.campaign_id)
        .join(Company, col(Company.upload_id) == col(Upload.id))
        .where(col(Company.id) == company_id)
    ).first()


def _first_member_job_id(members: list[DiscoveredContact], *, session: Session, company_id: UUID) -> UUID | None:
    for member in members:
        if member.contact_fetch_job_id is not None:
            return member.contact_fetch_job_id
    return session.exec(
        select(ContactFetchJob.id)
        .where(col(ContactFetchJob.company_id) == company_id)
        .order_by(col(ContactFetchJob.updated_at).desc())
    ).first()


def _find_existing_contact(
    *,
    session: Session,
    company_id: UUID,
    contact_entry: dict[str, Any],
) -> ProspectContact | None:
    email_normalized = _normalize_email(contact_entry.get("email"))
    if email_normalized:
        by_email = session.exec(
            select(ProspectContact)
            .join(ProspectContactEmail, col(ProspectContactEmail.contact_id) == col(ProspectContact.id))
            .where(
                col(ProspectContact.company_id) == company_id,
                col(ProspectContactEmail.email_normalized) == email_normalized,
            )
        ).first()
        if by_email:
            return by_email
        primary = session.exec(
            select(ProspectContact).where(
                col(ProspectContact.company_id) == company_id,
                func.lower(func.trim(col(ProspectContact.email))) == email_normalized,
            )
        ).first()
        if primary:
            return primary

    linkedin_url = (contact_entry.get("linkedin_url") or "").strip()
    if linkedin_url:
        by_linkedin = session.exec(
            select(ProspectContact).where(
                col(ProspectContact.company_id) == company_id,
                col(ProspectContact.linkedin_url) == linkedin_url,
            )
        ).first()
        if by_linkedin:
            return by_linkedin

    first_name = _normalize_name(contact_entry.get("first_name"))
    last_name = _normalize_name(contact_entry.get("last_name"))
    title = _normalize_name(contact_entry.get("title"))
    if not (first_name and last_name and title):
        return None
    for candidate in session.exec(
        select(ProspectContact).where(col(ProspectContact.company_id) == company_id)
    ):
        if _normalize_name(candidate.first_name) != first_name:
            continue
        if _normalize_name(candidate.last_name) != last_name:
            continue
        if _normalize_name(candidate.title) != title:
            continue
        return candidate
    return None


def _upsert_contact_email(
    *,
    session: Session,
    contact: ProspectContact,
    email: str | None,
    source: str,
    provider_email_status: str | None,
    set_primary_if_missing: bool = True,
) -> None:
    normalized = _normalize_email(email)
    if not normalized:
        return
    existing = session.exec(
        select(ProspectContactEmail).where(
            col(ProspectContactEmail.contact_id) == contact.id,
            col(ProspectContactEmail.email_normalized) == normalized,
        )
    ).first()
    if existing:
        existing.source = source
        if provider_email_status:
            existing.provider_email_status = provider_email_status
        existing.updated_at = utcnow()
        session.add(existing)
    else:
        session.add(
            ProspectContactEmail(
                contact_id=contact.id,
                source=source,
                email=normalized,
                email_normalized=normalized,
                provider_email_status=provider_email_status,
                is_primary=bool(set_primary_if_missing and not (contact.email or "").strip()),
            )
        )
    if set_primary_if_missing and not (contact.email or "").strip():
        contact.email = normalized
        contact.provider_email_status = provider_email_status
        session.add(contact)


@dataclass(frozen=True)
class DiscoveryProviderFetchResult:
    contacts: list[dict[str, Any]]
    title_matched_count: int
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class RevealProviderResult:
    contact_entry: dict[str, Any] | None = None
    revealed_count: int = 0
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

    # Compatibility shim: reveal workers now use ContactRevealService directly.
    def run_contact_reveal(self, *, engine: Any, job_id: UUID) -> ContactRevealJob | None:
        from app.services.contact_reveal_service import ContactRevealService

        return ContactRevealService().run_contact_reveal(engine=engine, job_id=job_id)

    def run_contact_reveal_apollo_attempt(self, *, engine: Any, attempt_id: UUID) -> ContactRevealAttempt | None:
        from app.services.contact_reveal_service import ContactRevealService

        return ContactRevealService().run_contact_reveal_apollo_attempt(engine=engine, attempt_id=attempt_id)

    def run_contact_reveal_snov_attempt(self, *, engine: Any, attempt_id: UUID) -> ContactRevealAttempt | None:
        from app.services.contact_reveal_service import ContactRevealService

        return ContactRevealService().run_contact_reveal_snov_attempt(engine=engine, attempt_id=attempt_id)

    def _run_reveal_attempt(self, *, engine: Any, attempt_id: UUID, provider: str) -> ContactRevealAttempt | None:
        now = utcnow()
        lock_token = str(uuid4())
        try:
            with Session(engine) as session:
                attempt = self._claim_reveal_attempt(
                    session=session,
                    attempt_id=attempt_id,
                    provider=provider,
                    lock_token=lock_token,
                    now=now,
                )
                if attempt is None:
                    return None
                job = session.get(ContactRevealJob, attempt.contact_reveal_job_id)
                if job is None:
                    return self._fail_reveal_attempt(
                        engine=engine,
                        attempt_id=attempt_id,
                        lock_token=lock_token,
                        error_code="contact_reveal_job_missing",
                        error_message="Parent reveal job not found.",
                    )
                company = session.get(Company, job.company_id)
                if company is None:
                    return self._fail_reveal_attempt(
                        engine=engine,
                        attempt_id=attempt_id,
                        lock_token=lock_token,
                        error_code="contact_company_missing",
                        error_message="Company not found.",
                    )
                members = self._load_reveal_members(session=session, job=job)
                provider_members = [member for member in members if member.provider == provider]
                if not provider_members:
                    return self._complete_reveal_attempt(
                        engine=engine,
                        attempt_id=attempt_id,
                        lock_token=lock_token,
                        revealed_count=0,
                    )

            decision = self._runtime.claim_provider_slot(provider)
            if decision.wait_seconds > 0:
                return self._defer_reveal_attempt(
                    engine=engine,
                    attempt_id=attempt_id,
                    lock_token=lock_token,
                    error_code=f"{provider}_backpressure",
                    error_message=decision.reason or "Provider is throttled.",
                    deferred_reason=decision.reason or "provider_backpressure",
                    delay_seconds=decision.wait_seconds,
                )

            result = (
                self._reveal_with_apollo(company=company, members=provider_members)
                if provider == "apollo"
                else self._reveal_with_snov(company=company, members=provider_members)
            )
            if result.error_code:
                if result.error_code in _PERMANENT_ERROR_CODES:
                    return self._fail_reveal_attempt(
                        engine=engine,
                        attempt_id=attempt_id,
                        lock_token=lock_token,
                        error_code=result.error_code,
                        error_message=result.error_message,
                    )
                delay_seconds = self._runtime.record_provider_error(provider, result.error_code)
                return self._defer_reveal_attempt(
                    engine=engine,
                    attempt_id=attempt_id,
                    lock_token=lock_token,
                    error_code=result.error_code,
                    error_message=result.error_message,
                    deferred_reason=result.error_code,
                    delay_seconds=delay_seconds,
                )

            self._runtime.record_provider_success(provider)
            revealed_count = 0
            if result.contact_entry is not None:
                revealed_count = self._persist_revealed_contact(
                    engine=engine,
                    company_id=company.id,
                    members=provider_members,
                    provider=provider,
                    contact_entry=result.contact_entry,
                )
            return self._complete_reveal_attempt(
                engine=engine,
                attempt_id=attempt_id,
                lock_token=lock_token,
                revealed_count=revealed_count,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "contact_reveal_attempt_unexpected_error", attempt_id=str(attempt_id), error=str(exc))
            delay_seconds = self._runtime.record_provider_error(provider, "provider_unexpected")
            return self._defer_reveal_attempt(
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
    # Reveal provider calls and revealed-contact persistence
    # ------------------------------------------------------------------

    def _reveal_with_apollo(self, *, company: Company, members: list[DiscoveredContact]) -> RevealProviderResult:
        member = next((item for item in members if item.provider_person_id), None)
        if member is None:
            return RevealProviderResult(revealed_count=0)
        person_details = _apollo.reveal_email(member.provider_person_id)
        if not person_details:
            if _apollo.last_error_code:
                return RevealProviderResult(
                    error_code=_apollo.last_error_code,
                    error_message=f"Apollo reveal failed: {_apollo.last_error_code}",
                )
            return RevealProviderResult(revealed_count=0)
        email = str(person_details.get("email") or "").strip() or None
        if not email:
            return RevealProviderResult(revealed_count=0)
        return RevealProviderResult(
            contact_entry={
                "first_name": str(person_details.get("first_name") or member.first_name).strip(),
                "last_name": str(person_details.get("last_name") or member.last_name).strip(),
                "title": str(person_details.get("title") or member.title or "").strip() or None,
                "title_match": True,
                "linkedin_url": str(person_details.get("linkedin_url") or member.linkedin_url or "").strip() or None,
                "email": email,
                "provider_email_status": str(person_details.get("email_status") or "verified").lower(),
                "verification_status": "unverified",
                "snov_confidence": None,
                "snov_prospect_raw": None,
                "apollo_prospect_raw": member.raw_payload_json,
                "snov_email_raw": None,
            },
            revealed_count=1,
        )

    def _reveal_with_snov(self, *, company: Company, members: list[DiscoveredContact]) -> RevealProviderResult:
        member = next((item for item in members if item.provider_person_id), None)
        if member is None:
            return RevealProviderResult(revealed_count=0)
        raw = member.raw_payload_json or {}
        search_url = str(raw.get("search_emails_start") or "").strip()
        prospect_hash = search_url.rstrip("/").rsplit("/", 1)[-1] if search_url else member.provider_person_id
        emails: list[dict[str, Any]] = []
        if prospect_hash:
            emails, error_code = _snov.search_prospect_email(prospect_hash)
            if error_code:
                return RevealProviderResult(
                    error_code=error_code,
                    error_message=f"Snov email search failed: {error_code}",
                )
        if not emails and member.first_name and member.last_name:
            emails, error_code = _snov.find_email_by_name(member.first_name, member.last_name, company.domain)
            if error_code:
                return RevealProviderResult(
                    error_code=error_code,
                    error_message=f"Snov email finder failed: {error_code}",
                )
        if not emails:
            return RevealProviderResult(revealed_count=0)
        best = emails[0]
        email = str(best.get("email") or "").strip() or None
        if not email:
            return RevealProviderResult(revealed_count=0)
        return RevealProviderResult(
            contact_entry={
                "first_name": member.first_name,
                "last_name": member.last_name,
                "title": member.title,
                "title_match": True,
                "linkedin_url": member.linkedin_url,
                "email": email,
                "provider_email_status": str(best.get("smtp_status") or "unknown").lower(),
                "verification_status": "unverified",
                "snov_confidence": None,
                "snov_prospect_raw": member.raw_payload_json,
                "apollo_prospect_raw": None,
                "snov_email_raw": emails,
            },
            revealed_count=1,
        )

    def _persist_revealed_contact(
        self,
        *,
        engine: Any,
        company_id: UUID,
        members: list[DiscoveredContact],
        provider: str,
        contact_entry: dict[str, Any],
    ) -> int:
        with Session(engine) as session:
            contact_fetch_job_id = _first_member_job_id(members, session=session, company_id=company_id)
            if contact_fetch_job_id is None:
                return 0
            existing = _find_existing_contact(
                session=session,
                company_id=company_id,
                contact_entry=contact_entry,
            )
            touched_contact_id: UUID | None = None
            if existing:
                existing.contact_fetch_job_id = contact_fetch_job_id
                existing.first_name = contact_entry["first_name"] or existing.first_name
                existing.last_name = contact_entry["last_name"] or existing.last_name
                existing.title = contact_entry["title"] or existing.title
                existing.title_match = bool(contact_entry["title_match"])
                existing.linkedin_url = contact_entry["linkedin_url"] or existing.linkedin_url
                existing.provider_email_status = (
                    contact_entry["provider_email_status"] or existing.provider_email_status
                )
                if contact_entry["snov_confidence"] is not None:
                    existing.snov_confidence = contact_entry["snov_confidence"]
                if contact_entry["snov_prospect_raw"] is not None:
                    existing.snov_prospect_raw = contact_entry["snov_prospect_raw"]
                if contact_entry["apollo_prospect_raw"] is not None:
                    existing.apollo_prospect_raw = contact_entry["apollo_prospect_raw"]
                if contact_entry["snov_email_raw"] is not None:
                    existing.snov_email_raw = contact_entry["snov_email_raw"]
                _upsert_contact_email(
                    session=session,
                    contact=existing,
                    email=contact_entry.get("email"),
                    source=provider,
                    provider_email_status=contact_entry.get("provider_email_status"),
                )
                existing.source = provider
                existing.updated_at = utcnow()
                session.add(existing)
                touched_contact_id = existing.id
            else:
                new_contact = ProspectContact(
                    company_id=company_id,
                    contact_fetch_job_id=contact_fetch_job_id,
                    source=provider,
                    first_name=contact_entry["first_name"],
                    last_name=contact_entry["last_name"],
                    title=contact_entry["title"],
                    title_match=bool(contact_entry["title_match"]),
                    linkedin_url=contact_entry["linkedin_url"],
                    email=contact_entry["email"],
                    provider_email_status=contact_entry["provider_email_status"],
                    verification_status=contact_entry["verification_status"],
                    snov_confidence=contact_entry["snov_confidence"],
                    snov_prospect_raw=contact_entry["snov_prospect_raw"],
                    apollo_prospect_raw=contact_entry["apollo_prospect_raw"],
                    snov_email_raw=contact_entry["snov_email_raw"],
                )
                session.add(new_contact)
                session.flush()
                _upsert_contact_email(
                    session=session,
                    contact=new_contact,
                    email=contact_entry.get("email"),
                    source=provider,
                    provider_email_status=contact_entry.get("provider_email_status"),
                )
                touched_contact_id = new_contact.id
            if touched_contact_id is not None:
                recompute_contact_stages(session, contact_ids=[touched_contact_id])
            session.commit()
        return 1

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
        if job.state == ContactFetchJobState.SUCCEEDED and contacts_found > 0:
            enqueue_s4_for_contact_success(engine=engine, contact_fetch_job_id=job.id)
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
    # Reveal job state helpers
    # ------------------------------------------------------------------

    def _claim_reveal_job(
        self,
        *,
        session: Session,
        job_id: UUID,
        lock_token: str,
        now: datetime,
    ) -> ContactRevealJob | None:
        session.execute(
            sa_update(ContactRevealJob)
            .where(
                col(ContactRevealJob.id) == job_id,
                col(ContactRevealJob.terminal_state).is_(False),
                col(ContactRevealJob.state).in_([ContactFetchJobState.QUEUED, ContactFetchJobState.RUNNING]),
                or_(
                    col(ContactRevealJob.lock_token).is_(None),
                    col(ContactRevealJob.lock_expires_at) < now,
                ),
            )
            .values(
                state=ContactFetchJobState.RUNNING,
                attempt_count=col(ContactRevealJob.attempt_count) + 1,
                lock_token=lock_token,
                lock_expires_at=now + _CONTACT_LOCK_TTL,
                last_error_code=None,
                last_error_message=None,
                updated_at=now,
            )
        )
        session.commit()
        job = session.get(ContactRevealJob, job_id)
        if job is None or job.lock_token != lock_token:
            return None
        if not job.started_at:
            job.started_at = now
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    def _ensure_reveal_attempts(
        self,
        *,
        session: Session,
        job: ContactRevealJob,
        requested_providers: list[str],
    ) -> None:
        existing = {
            attempt.provider: attempt
            for attempt in session.exec(
                select(ContactRevealAttempt).where(
                    col(ContactRevealAttempt.contact_reveal_job_id) == job.id
                )
            )
        }
        for index, provider in enumerate(requested_providers):
            if provider in existing:
                continue
            session.add(
                ContactRevealAttempt(
                    contact_reveal_job_id=job.id,
                    provider=provider,
                    sequence_index=index,
                    max_attempts=max(5, job.max_attempts),
                )
            )
        session.commit()

    def _claim_reveal_attempt(
        self,
        *,
        session: Session,
        attempt_id: UUID,
        provider: str,
        lock_token: str,
        now: datetime,
    ) -> ContactRevealAttempt | None:
        session.execute(
            sa_update(ContactRevealAttempt)
            .where(
                col(ContactRevealAttempt.id) == attempt_id,
                col(ContactRevealAttempt.provider) == provider,
                col(ContactRevealAttempt.terminal_state).is_(False),
                col(ContactRevealAttempt.state).in_(
                    [
                        ContactProviderAttemptState.QUEUED,
                        ContactProviderAttemptState.DEFERRED,
                        ContactProviderAttemptState.RUNNING,
                    ]
                ),
                or_(
                    col(ContactRevealAttempt.lock_token).is_(None),
                    col(ContactRevealAttempt.lock_expires_at) < now,
                ),
            )
            .values(
                state=ContactProviderAttemptState.RUNNING,
                attempt_count=col(ContactRevealAttempt.attempt_count) + 1,
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
        attempt = session.get(ContactRevealAttempt, attempt_id)
        if attempt is None or attempt.lock_token != lock_token:
            return None
        if not attempt.started_at:
            attempt.started_at = now
            session.add(attempt)
            session.commit()
            session.refresh(attempt)
        return attempt

    def _load_reveal_members(self, *, session: Session, job: ContactRevealJob) -> list[DiscoveredContact]:
        member_ids: list[UUID] = []
        for raw in job.discovered_contact_ids_json or []:
            try:
                member_ids.append(UUID(str(raw)))
            except (TypeError, ValueError):
                continue
        if not member_ids:
            return []
        return list(
            session.exec(
                select(DiscoveredContact).where(col(DiscoveredContact.id).in_(member_ids))
            )
        )

    def _release_reveal_job(
        self,
        *,
        session: Session,
        job: ContactRevealJob,
        state: ContactFetchJobState,
    ) -> None:
        job.state = state
        job.terminal_state = False
        job.lock_token = None
        job.lock_expires_at = None
        job.updated_at = utcnow()
        session.add(job)

    def _finalize_reveal_job(self, *, session: Session, job: ContactRevealJob) -> ContactRevealJob:
        attempts = list(
            session.exec(
                select(ContactRevealAttempt).where(
                    col(ContactRevealAttempt.contact_reveal_job_id) == job.id
                )
            )
        )
        revealed_count = sum(int(attempt.revealed_count or 0) for attempt in attempts)
        first_error = next(
            (
                (attempt.last_error_code, attempt.last_error_message)
                for attempt in attempts
                if attempt.last_error_code
            ),
            (None, None),
        )
        if revealed_count > 0:
            job.state = ContactFetchJobState.SUCCEEDED
            job.last_error_code = None
            job.last_error_message = None
        elif any(attempt.state == ContactProviderAttemptState.DEAD for attempt in attempts):
            job.state = ContactFetchJobState.DEAD
            job.last_error_code = first_error[0] or "no_email_revealed"
            job.last_error_message = first_error[1]
        elif any(attempt.state == ContactProviderAttemptState.FAILED for attempt in attempts):
            job.state = ContactFetchJobState.FAILED
            job.last_error_code = first_error[0] or "no_email_revealed"
            job.last_error_message = first_error[1]
        else:
            job.state = ContactFetchJobState.FAILED
            job.last_error_code = "no_email_revealed"
            job.last_error_message = "No provider returned an email for this contact group."
        job.terminal_state = True
        job.revealed_count = revealed_count
        job.finished_at = utcnow()
        job.updated_at = utcnow()
        job.lock_token = None
        job.lock_expires_at = None
        session.add(job)
        self._refresh_reveal_batch_state(session, batch_id=job.contact_reveal_batch_id)
        return job

    def _refresh_reveal_batch_state(self, session: Session, *, batch_id: UUID | None) -> None:
        if batch_id is None:
            return
        batch = session.get(ContactRevealBatch, batch_id)
        if batch is None:
            return
        jobs = list(
            session.exec(
                select(ContactRevealJob).where(col(ContactRevealJob.contact_reveal_batch_id) == batch_id)
            )
        )
        if not jobs:
            batch.state = ContactFetchBatchState.COMPLETED
        elif all(job.terminal_state for job in jobs):
            if any(job.state == ContactFetchJobState.SUCCEEDED for job in jobs):
                batch.state = ContactFetchBatchState.COMPLETED
                batch.last_error_code = None
                batch.last_error_message = None
            else:
                batch.state = ContactFetchBatchState.FAILED
                first_error = next(
                    (
                        (job.last_error_code, job.last_error_message)
                        for job in jobs
                        if job.last_error_code
                    ),
                    (None, None),
                )
                batch.last_error_code = first_error[0]
                batch.last_error_message = first_error[1]
            batch.finished_at = utcnow()
        elif any(job.state == ContactFetchJobState.RUNNING for job in jobs):
            batch.state = ContactFetchBatchState.RUNNING
        else:
            batch.state = ContactFetchBatchState.QUEUED
        batch.updated_at = utcnow()
        session.add(batch)

    def _mark_reveal_job_failure(
        self,
        *,
        engine: Any,
        job_id: UUID,
        lock_token: str,
        error_code: str,
        error_message: str,
    ) -> ContactRevealJob | None:
        with Session(engine) as session:
            job = session.get(ContactRevealJob, job_id)
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
            self._refresh_reveal_batch_state(session, batch_id=job.contact_reveal_batch_id)
            session.commit()
            session.refresh(job)
            return job

    def _complete_reveal_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        lock_token: str,
        revealed_count: int,
    ) -> ContactRevealAttempt | None:
        dispatch_job_id: UUID | None = None
        with Session(engine) as session:
            attempt = session.get(ContactRevealAttempt, attempt_id)
            if attempt is None or attempt.lock_token != lock_token:
                return attempt
            attempt.state = ContactProviderAttemptState.SUCCEEDED
            attempt.terminal_state = True
            attempt.revealed_count = revealed_count
            attempt.deferred_reason = None
            attempt.next_retry_at = None
            attempt.last_error_code = None
            attempt.last_error_message = None
            attempt.lock_token = None
            attempt.lock_expires_at = None
            attempt.finished_at = utcnow()
            attempt.updated_at = utcnow()
            session.add(attempt)
            job = session.get(ContactRevealJob, attempt.contact_reveal_job_id)
            if job is not None:
                dispatch_job_id = job.id
            session.commit()
            session.refresh(attempt)
        if dispatch_job_id:
            self._dispatch_reveal_job(job_id=dispatch_job_id)
        return attempt

    def _defer_reveal_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        lock_token: str,
        error_code: str,
        error_message: str,
        deferred_reason: str,
        delay_seconds: int,
    ) -> ContactRevealAttempt | None:
        dispatch_job_id: UUID | None = None
        with Session(engine) as session:
            attempt = session.get(ContactRevealAttempt, attempt_id)
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
            job = session.get(ContactRevealJob, attempt.contact_reveal_job_id)
            if job is not None:
                dispatch_job_id = job.id
            session.commit()
            session.refresh(attempt)
        if dispatch_job_id:
            self._dispatch_reveal_job(job_id=dispatch_job_id)
        return attempt

    def _fail_reveal_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        lock_token: str,
        error_code: str,
        error_message: str,
    ) -> ContactRevealAttempt | None:
        dispatch_job_id: UUID | None = None
        with Session(engine) as session:
            attempt = session.get(ContactRevealAttempt, attempt_id)
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
            job = session.get(ContactRevealJob, attempt.contact_reveal_job_id)
            if job is not None:
                dispatch_job_id = job.id
            session.commit()
            session.refresh(attempt)
        if dispatch_job_id:
            self._dispatch_reveal_job(job_id=dispatch_job_id)
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

    def _dispatch_reveal_job(self, *, job_id: UUID) -> None:
        from app.tasks.contacts import reveal_contact_emails

        reveal_contact_emails.delay(str(job_id))

    def _dispatch_reveal_attempt(self, *, attempt: ContactRevealAttempt) -> None:
        from app.tasks.contacts import reveal_contact_apollo_attempt, reveal_contact_snov_attempt

        if attempt.provider == "apollo":
            reveal_contact_apollo_attempt.delay(str(attempt.id))
        else:
            reveal_contact_snov_attempt.delay(str(attempt.id))
