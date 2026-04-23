"""ContactFetchJob execution: CAS-claim, Snov.io/Apollo prospect fetch, write results.

Three-phase pattern (same as AnalysisService):
  Phase 1 — CAS-claim job + load company domain + load title rules (short DB session)
  Phase 2 — Provider API calls: fetch prospects → filter by title → fetch emails (no DB)
  Phase 3 — Upsert ProspectContact rows + mark job terminal (new short DB session)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models import Company, ContactFetchJob, ContactProviderAttempt, ProspectContact, ProspectContactEmail, TitleMatchRule
from app.models.pipeline import ContactFetchJobState, ContactProviderAttemptState
from app.services.pipeline_service import recompute_contact_stages
from app.services.pipeline_run_orchestrator import enqueue_s4_for_contact_success
from app.services.apollo_client import (
    ERR_APOLLO_AUTH_FAILED,
    ERR_APOLLO_CREDENTIALS_MISSING,
    ERR_APOLLO_FAILED,
    ERR_APOLLO_RATE_LIMITED,
    ERR_APOLLO_TIMEOUT,
    ApolloClient,
)
from app.services.contact_queue_service import ContactQueueService
from app.services.contact_runtime_service import ContactRuntimeService
from app.services.snov_client import (
    ERR_SNOV_AUTH_FAILED,
    ERR_SNOV_CREDENTIALS_MISSING,
    ERR_SNOV_FAILED,
    ERR_SNOV_RATE_LIMITED,
    ERR_SNOV_TIMEOUT,
    SnovClient,
)

logger = logging.getLogger(__name__)

_CONTACT_LOCK_TTL = timedelta(minutes=15)

# These error codes mean the credentials are wrong or missing — don't retry.
_PERMANENT_ERROR_CODES: frozenset[str] = frozenset({
    ERR_SNOV_CREDENTIALS_MISSING,
    ERR_SNOV_AUTH_FAILED,
    ERR_APOLLO_CREDENTIALS_MISSING,
    ERR_APOLLO_AUTH_FAILED,
})
_TRANSIENT_ERROR_CODES: frozenset[str] = frozenset({
    ERR_SNOV_RATE_LIMITED,
    ERR_SNOV_TIMEOUT,
    ERR_SNOV_FAILED,
    ERR_APOLLO_RATE_LIMITED,
    ERR_APOLLO_TIMEOUT,
    ERR_APOLLO_FAILED,
    "provider_unexpected",
    "contact_job_unexpected",
})

_snov = SnovClient()
_apollo = ApolloClient()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Title matching ────────────────────────────────────────────────────────────

_TITLE_SYNONYMS: dict[str, str] = {
    "vp": "vice president",
    "svp": "senior vice president",
    "evp": "executive vice president",
    "avp": "assistant vice president",
    "cmo": "chief marketing officer",
    "cto": "chief technology officer",
    "cio": "chief information officer",
    "cdo": "chief digital officer",
    "coo": "chief operating officer",
    "cfo": "chief financial officer",
    "cro": "chief revenue officer",
    "cpo": "chief product officer",
    "ceo": "chief executive officer",
    "gm": "general manager",
}


def _normalize_title(title: str) -> str:
    normalized = title.lower()
    for abbreviation, replacement in _TITLE_SYNONYMS.items():
        normalized = re.sub(r"\b" + re.escape(abbreviation) + r"\b", replacement, normalized)
    return normalized


def match_title(
    title: str,
    include_rules: list[list[str]],
    exclude_words: list[str],
) -> bool:
    """Return True if the title matches the rules.

    Logic:
    - Exclude first: any exclude keyword present → False
    - Include: any rule where ALL keywords appear in title → True
      Special rule entry ['__regex__:<pattern>'] is matched as a regex.
    """
    if not title:
        return False
    lowered = _normalize_title(title.lower())
    normalized_excludes = [_normalize_title(word.strip()) for word in exclude_words if word.strip()]
    if any(re.search(r"\b" + re.escape(word) + r"\b", lowered) for word in normalized_excludes):
        return False
    for keywords in include_rules:
        if len(keywords) == 1 and keywords[0].startswith("__regex__:"):
            pattern = keywords[0][len("__regex__:"):]
            if re.search(pattern, lowered, re.IGNORECASE):
                return True
        elif all(re.search(r"\b" + re.escape(_normalize_title(kw)) + r"\b", lowered) for kw in keywords):
            return True
    return False


def load_title_rules(
    session: Session,
) -> tuple[list[list[str]], list[str]]:
    """Load include/exclude rules from DB. Returns (include_rules, exclude_words).

    include_rules entries:
    - keyword (default): [kw1, kw2, ...] — all must match (AND logic)
    - regex: ['__regex__:<pattern>'] — marker recognized by match_title
    - seniority: each preset keyword becomes its own single-element rule (OR logic)
    """
    rules = list(session.exec(select(TitleMatchRule)))
    include_rules: list[list[str]] = []
    exclude_words: list[str] = []
    for rule in rules:
        mt = getattr(rule, "match_type", "keyword") or "keyword"
        if rule.rule_type == "include":
            if mt == "regex":
                include_rules.append([f"__regex__:{rule.keywords.strip()}"])
            elif mt == "seniority":
                for kw in SENIORITY_PRESETS.get(rule.keywords.strip(), []):
                    include_rules.append([_normalize_title(kw)])
            else:
                kws = [_normalize_title(k.strip()) for k in rule.keywords.split(",") if k.strip()]
                if kws:
                    include_rules.append(kws)
        elif rule.rule_type == "exclude":
            kws = [_normalize_title(k.strip()) for k in rule.keywords.split(",") if k.strip()]
            exclude_words.extend(kws)
    return include_rules, exclude_words


SENIORITY_PRESETS: dict[str, list[str]] = {
    "c_level": ["chief", "ceo", "cto", "cmo", "coo", "cfo", "cdo", "cio", "cro", "cpo"],
    "vp_level": ["vice president", "vp", "svp", "evp"],
    "director_level": ["director"],
    "manager_level": ["manager"],
    "senior_ic": ["senior", "lead", "principal", "staff"],
}

# ── Seed data ─────────────────────────────────────────────────────────────────

SEED_INCLUDE_RULES: list[str] = [
    "marketing, director",
    "marketing, vp",
    "marketing, vice president",
    "chief marketing officer",
    "marketing head",
    "owner",
    "founder",
    "cmo",
    "gm",
    "general manager",
    "e-commerce",
    "ecommerce",
    "IT, director",
    "IT, vp",
    "IT, vice president",
    "chief digital officer",
    "cdo",
    "chief technology officer",
    "cto",
    "cio",
    "chief information officer",
    "webmaster",
    "digital marketing, director",
    "digital marketing, vp",
]

SEED_EXCLUDE_RULES: list[str] = [
    "representative",
    "associate",
    "executive",
    "assistant",
]


def rematch_existing_contacts(session: Session) -> tuple[int, list[UUID]]:
    """Re-apply current title rules to all existing ProspectContact rows.

    Returns (updated_count, company_ids_needing_email_fetch).
    company_ids_needing_email_fetch contains companies that now have title_match=True
    contacts with no email — callers should enqueue a ContactFetchJob for these.
    """
    include_rules, exclude_words = load_title_rules(session)
    contacts = list(session.exec(select(ProspectContact)))
    updated = 0
    touched_ids: list[UUID] = []
    companies_needing_fetch: set[UUID] = set()
    for contact in contacts:
        new_match = match_title(contact.title or "", include_rules, exclude_words) if include_rules else False
        if contact.title_match != new_match:
            contact.title_match = new_match
            contact.updated_at = utcnow()
            session.add(contact)
            updated += 1
            touched_ids.append(contact.id)
        if new_match and not contact.email:
            companies_needing_fetch.add(contact.company_id)
    if updated:
        recompute_contact_stages(session, contact_ids=touched_ids)
        session.commit()
    return updated, list(companies_needing_fetch)


def seed_title_rules(session: Session) -> int:
    """Insert default title match rules. Skips rows that already exist. Returns count inserted."""
    existing = set(session.exec(select(TitleMatchRule.keywords)).all())
    inserted = 0
    for kws in SEED_INCLUDE_RULES:
        if kws not in existing:
            session.add(TitleMatchRule(rule_type="include", keywords=kws))
            inserted += 1
    for kws in SEED_EXCLUDE_RULES:
        if kws not in existing:
            session.add(TitleMatchRule(rule_type="exclude", keywords=kws))
            inserted += 1
    session.commit()
    return inserted


def _extract_apollo_title_filter(session: Session) -> list[str]:
    """Build Apollo person_titles filter from include rules.

    Each include rule (e.g., "marketing, director") becomes one title phrase
    ("marketing director"). Returns an empty list when no include rules exist,
    meaning: fetch all contacts and filter locally.
    """
    rules = list(session.exec(
        select(TitleMatchRule).where(col(TitleMatchRule.rule_type) == "include")
    ))
    phrases: list[str] = []
    for rule in rules:
        kws = [k.strip() for k in rule.keywords.split(",") if k.strip()]
        if kws:
            phrases.append(" ".join(kws))
    seen: set[str] = set()
    result: list[str] = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def test_title_match_detailed(title: str, session: Session) -> dict:
    """Test a title against all current rules; return which rules triggered."""
    rules = list(session.exec(select(TitleMatchRule)))
    normalized = _normalize_title(title)

    exclude_kws: list[str] = []
    for r in rules:
        if r.rule_type == "exclude":
            exclude_kws.extend(_normalize_title(k.strip()) for k in r.keywords.split(",") if k.strip())

    excluded_by = [
        kw for kw in exclude_kws
        if re.search(r"\b" + re.escape(kw) + r"\b", normalized)
    ]

    matching_rules: list[str] = []
    if not excluded_by:
        for r in rules:
            if r.rule_type != "include":
                continue
            mt = getattr(r, "match_type", "keyword") or "keyword"
            if mt == "regex":
                if re.search(r.keywords.strip(), normalized, re.IGNORECASE):
                    matching_rules.append(f"regex: {r.keywords}")
            elif mt == "seniority":
                preset_kws = SENIORITY_PRESETS.get(r.keywords.strip(), [])
                if any(
                    re.search(r"\b" + re.escape(_normalize_title(kw)) + r"\b", normalized)
                    for kw in preset_kws
                ):
                    matching_rules.append(f"seniority({r.keywords})")
            else:
                kws = [_normalize_title(k.strip()) for k in r.keywords.split(",") if k.strip()]
                if kws and all(re.search(r"\b" + re.escape(kw) + r"\b", normalized) for kw in kws):
                    matching_rules.append(r.keywords)

    return {
        "matched": bool(matching_rules),
        "matching_rules": matching_rules,
        "excluded_by": excluded_by,
        "normalized_title": normalized,
    }


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _normalize_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _find_existing_contact(
    *,
    session: Session,
    company_id: UUID,
    contact_entry: dict[str, Any],
) -> ProspectContact | None:
    email_normalized = _normalize_email(contact_entry.get("email"))
    if email_normalized:
        existing_contact_by_email = session.exec(
            select(ProspectContact)
            .join(ProspectContactEmail, col(ProspectContactEmail.contact_id) == col(ProspectContact.id))
            .where(
                col(ProspectContact.company_id) == company_id,
                col(ProspectContactEmail.email_normalized) == email_normalized,
            )
        ).first()
        if existing_contact_by_email:
            return existing_contact_by_email
        existing_primary = session.exec(
            select(ProspectContact).where(
                col(ProspectContact.company_id) == company_id,
                func.lower(func.trim(col(ProspectContact.email))) == email_normalized,
            )
        ).first()
        if existing_primary:
            return existing_primary

    linkedin_url = (contact_entry.get("linkedin_url") or "").strip()
    if linkedin_url:
        existing_linkedin = session.exec(
            select(ProspectContact).where(
                col(ProspectContact.company_id) == company_id,
                col(ProspectContact.linkedin_url) == linkedin_url,
            )
        ).first()
        if existing_linkedin:
            return existing_linkedin

    first_name = _normalize_name(contact_entry.get("first_name"))
    last_name = _normalize_name(contact_entry.get("last_name"))
    title = _normalize_name(contact_entry.get("title"))
    if first_name and last_name and title:
        candidates = list(
            session.exec(
                select(ProspectContact).where(col(ProspectContact.company_id) == company_id)
            )
        )
        for candidate in candidates:
            if _normalize_name(candidate.first_name) != first_name:
                continue
            if _normalize_name(candidate.last_name) != last_name:
                continue
            candidate_title = _normalize_name(candidate.title)
            if not candidate_title:
                continue
            if candidate_title != title:
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


def compute_title_rule_stats(session: Session) -> dict:
    """Compute per-rule contact match counts."""
    rules = list(session.exec(
        select(TitleMatchRule).order_by(col(TitleMatchRule.rule_type), col(TitleMatchRule.created_at))
    ))
    titles = list(session.exec(
        select(ProspectContact.title)
        .where(col(ProspectContact.title).is_not(None))
    ).all())
    titles = [t for t in titles if t]

    total_contacts = len(titles)
    include_rules, exclude_words = load_title_rules(session)
    total_matched = sum(1 for t in titles if match_title(t, include_rules, exclude_words))

    rule_stats = []
    for r in rules:
        mt = getattr(r, "match_type", "keyword") or "keyword"
        if r.rule_type == "include":
            if mt == "regex":
                count = sum(
                    1 for t in titles
                    if re.search(r.keywords.strip(), _normalize_title(t), re.IGNORECASE)
                )
            elif mt == "seniority":
                preset_kws = [_normalize_title(kw) for kw in SENIORITY_PRESETS.get(r.keywords.strip(), [])]
                count = sum(
                    1 for t in titles
                    if any(
                        re.search(r"\b" + re.escape(kw) + r"\b", _normalize_title(t))
                        for kw in preset_kws
                    )
                )
            else:
                kws = [_normalize_title(k.strip()) for k in r.keywords.split(",") if k.strip()]
                count = sum(
                    1 for t in titles
                    if kws and all(re.search(r"\b" + re.escape(kw) + r"\b", _normalize_title(t)) for kw in kws)
                )
        else:
            kws = [_normalize_title(k.strip()) for k in r.keywords.split(",") if k.strip()]
            count = sum(
                1 for t in titles
                if any(re.search(r"\b" + re.escape(kw) + r"\b", _normalize_title(t)) for kw in kws)
            )
        rule_stats.append({
            "rule_id": r.id,
            "rule_type": r.rule_type,
            "keywords": r.keywords,
            "contact_match_count": count,
        })

    return {"rules": rule_stats, "total_contacts": total_contacts, "total_matched": total_matched}


# ── ContactService ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContactProviderFetchResult:
    contacts: list[dict[str, Any]]
    title_matched_count: int
    error_code: str = ""
    error_message: str = ""


class ContactService:
    def __init__(self) -> None:
        self._runtime = ContactRuntimeService()
        self._queue = ContactQueueService()

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
                job = self._claim_contact_job(
                    session=session,
                    job_id=job_id,
                    lock_token=lock_token,
                    now=now,
                )
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
                if job.provider != requested_providers[0]:
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
                        and attempt.state in {
                            ContactProviderAttemptState.QUEUED,
                            ContactProviderAttemptState.DEFERRED,
                        }
                        and (attempt.next_retry_at is None or attempt.next_retry_at <= now)
                    )
                ]
                waiting_on_future_retry = any(
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

                if running_attempt or waiting_on_future_retry:
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

                finalized_job = self._finalize_contact_job(session=session, job=job)
                session.commit()
                session.refresh(finalized_job)

            if finalized_job.state == ContactFetchJobState.SUCCEEDED:
                enqueue_s4_for_contact_success(engine=engine, contact_fetch_job_id=finalized_job.id)
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

    def _run_provider_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        provider: str,
    ) -> ContactProviderAttempt | None:
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

                include_rules, exclude_words = load_title_rules(session)
                apollo_title_filter = (
                    _extract_apollo_title_filter(session) if provider == "apollo" else []
                )

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
                    apollo_title_filter=apollo_title_filter,
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
            contacts_written = self._persist_contacts(
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
                col(ContactFetchJob.state).in_([
                    ContactFetchJobState.QUEUED,
                    ContactFetchJobState.RUNNING,
                ]),
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
                col(ContactProviderAttempt.state).in_([
                    ContactProviderAttemptState.QUEUED,
                    ContactProviderAttemptState.DEFERRED,
                    ContactProviderAttemptState.RUNNING,
                ]),
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

    def _requested_providers(self, *, job: ContactFetchJob, legacy_provider: str) -> list[str]:
        allowed = {"snov", "apollo"}
        requested = [
            str(provider).strip().lower()
            for provider in (job.requested_providers_json or [])
            if str(provider).strip().lower() in allowed
        ]
        if requested:
            return list(dict.fromkeys(requested))

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

    def _finalize_contact_job(self, *, session: Session, job: ContactFetchJob) -> ContactFetchJob:
        attempts = list(
            session.exec(
                select(ContactProviderAttempt).where(
                    col(ContactProviderAttempt.contact_fetch_job_id) == job.id
                )
            )
        )
        contacts_found = session.exec(
            select(func.count(ProspectContact.id)).where(
                col(ProspectContact.contact_fetch_job_id) == job.id
            )
        ).one() or 0
        title_matched_count = session.exec(
            select(func.count(ProspectContact.id)).where(
                col(ProspectContact.contact_fetch_job_id) == job.id,
                col(ProspectContact.title_match).is_(True),
            )
        ).one() or 0
        any_success = any(attempt.state == ContactProviderAttemptState.SUCCEEDED for attempt in attempts)
        first_error = next(
            (
                (attempt.last_error_code, attempt.last_error_message)
                for attempt in attempts
                if attempt.last_error_code
            ),
            (None, None),
        )
        if any_success:
            job.state = ContactFetchJobState.SUCCEEDED
            job.last_error_code = None
            job.last_error_message = None
        elif any(attempt.state == ContactProviderAttemptState.DEAD for attempt in attempts):
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
        job.terminal_state = True
        job.contacts_found = int(contacts_found)
        job.title_matched_count = int(title_matched_count)
        job.finished_at = utcnow()
        job.updated_at = utcnow()
        job.lock_token = None
        job.lock_expires_at = None
        session.add(job)
        recompute_contact_stages(session, company_ids=[job.company_id])
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
                job.state = (
                    ContactFetchJobState.FAILED
                    if error_code in _PERMANENT_ERROR_CODES
                    else ContactFetchJobState.DEAD
                )
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
            attempt.state = (
                ContactProviderAttemptState.FAILED
                if error_code in _PERMANENT_ERROR_CODES
                else ContactProviderAttemptState.DEAD
            )
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

    def _persist_contacts(
        self,
        *,
        engine: Any,
        job_id: UUID,
        company_id: UUID,
        provider: str,
        contacts_to_write: list[dict[str, Any]],
    ) -> int:
        contacts_written = 0
        with Session(engine) as session:
            job = session.get(ContactFetchJob, job_id)
            if job is None:
                return 0
            for contact_entry in contacts_to_write:
                existing = _find_existing_contact(
                    session=session,
                    company_id=company_id,
                    contact_entry=contact_entry,
                )
                if existing:
                    existing.contact_fetch_job_id = job_id
                    existing.first_name = contact_entry["first_name"] or existing.first_name
                    existing.last_name = contact_entry["last_name"] or existing.last_name
                    existing.title = contact_entry["title"] or existing.title
                    existing.title_match = contact_entry["title_match"]
                    existing.linkedin_url = contact_entry["linkedin_url"] or existing.linkedin_url
                    existing.provider_email_status = (
                        contact_entry["provider_email_status"] or existing.provider_email_status
                    )
                    if contact_entry["snov_confidence"] is not None:
                        existing.snov_confidence = contact_entry["snov_confidence"]
                    if contact_entry["snov_prospect_raw"] is not None:
                        existing.snov_prospect_raw = contact_entry["snov_prospect_raw"]
                    if contact_entry.get("apollo_prospect_raw") is not None:
                        existing.apollo_prospect_raw = contact_entry.get("apollo_prospect_raw")
                    if contact_entry["snov_email_raw"] is not None:
                        existing.snov_email_raw = contact_entry["snov_email_raw"]
                    if existing.email:
                        _upsert_contact_email(
                            session=session,
                            contact=existing,
                            email=existing.email,
                            source=existing.source or provider,
                            provider_email_status=existing.provider_email_status,
                            set_primary_if_missing=False,
                        )
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
                else:
                    new_contact = ProspectContact(
                        company_id=company_id,
                        contact_fetch_job_id=job_id,
                        source=provider,
                        first_name=contact_entry["first_name"],
                        last_name=contact_entry["last_name"],
                        title=contact_entry["title"],
                        title_match=contact_entry["title_match"],
                        linkedin_url=contact_entry["linkedin_url"],
                        email=contact_entry["email"],
                        provider_email_status=contact_entry["provider_email_status"],
                        verification_status=contact_entry["verification_status"],
                        snov_confidence=contact_entry["snov_confidence"],
                        snov_prospect_raw=contact_entry["snov_prospect_raw"],
                        apollo_prospect_raw=contact_entry.get("apollo_prospect_raw"),
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
                contacts_written += 1
            session.commit()
        return contacts_written

    def _fetch_apollo_contacts(
        self,
        *,
        domain: str,
        include_rules: list[list[str]],
        exclude_words: list[str],
        apollo_title_filter: list[str],
    ) -> ContactProviderFetchResult:
        all_prospects: list[dict[str, Any]] = []
        contacts_to_write: list[dict[str, Any]] = []
        title_matched_count = 0

        for page in range(1, 4):
            prospects = _apollo.search_people(
                domain,
                page=page,
                person_titles=apollo_title_filter if apollo_title_filter else None,
            )
            apollo_err = _apollo.last_error_code
            if not prospects:
                if apollo_err:
                    return ContactProviderFetchResult(
                        contacts=[],
                        title_matched_count=0,
                        error_code=apollo_err,
                        error_message=f"Apollo search failed: {apollo_err}",
                    )
                break
            all_prospects.extend(prospects)
            if len(prospects) < 100:
                break

        if not all_prospects:
            return ContactProviderFetchResult(contacts=[], title_matched_count=0)

        for prospect in all_prospects:
            first_name = str(prospect.get("first_name") or "").strip()
            last_name = str(prospect.get("last_name") or prospect.get("last_name_obfuscated") or "").strip()
            title = str(prospect.get("title") or prospect.get("position") or "").strip()
            linkedin_url = str(prospect.get("linkedin_url") or "").strip() or None
            title_matched = match_title(title, include_rules, exclude_words) if include_rules else False
            if not title_matched:
                continue
            title_matched_count += 1

            person_id = str(prospect.get("id") or "").strip()
            if not person_id or not prospect.get("has_email"):
                continue

            person_details = _apollo.reveal_email(person_id)
            if not person_details:
                if _apollo.last_error_code:
                    return ContactProviderFetchResult(
                        contacts=[],
                        title_matched_count=title_matched_count,
                        error_code=_apollo.last_error_code,
                        error_message=f"Apollo reveal failed: {_apollo.last_error_code}",
                    )
                continue

            email = str(person_details.get("email") or "").strip() or None
            if not email:
                continue

            contacts_to_write.append(
                {
                    "first_name": str(person_details.get("first_name") or first_name).strip(),
                    "last_name": str(person_details.get("last_name") or last_name).strip(),
                    "title": str(person_details.get("title") or title).strip() or None,
                    "title_match": True,
                    "linkedin_url": str(person_details.get("linkedin_url") or linkedin_url or "").strip() or None,
                    "email": email,
                    "provider_email_status": str(person_details.get("email_status") or "verified").lower(),
                    "verification_status": "unverified",
                    "snov_confidence": None,
                    "snov_prospect_raw": None,
                    "apollo_prospect_raw": prospect,
                    "snov_email_raw": None,
                }
            )

        return ContactProviderFetchResult(
            contacts=contacts_to_write,
            title_matched_count=title_matched_count,
        )

    def _fetch_snov_contacts(
        self,
        *,
        domain: str,
        include_rules: list[list[str]],
        exclude_words: list[str],
    ) -> ContactProviderFetchResult:
        count, err = _snov.get_domain_email_count(domain)
        if err:
            return ContactProviderFetchResult(
                contacts=[],
                title_matched_count=0,
                error_code=err,
                error_message=f"Snov domain count failed: {err}",
            )
        if count == 0:
            log_event(logger, "contact_fetch_no_emails", domain=domain)
            return ContactProviderFetchResult(contacts=[], title_matched_count=0)

        all_prospects: list[dict[str, Any]] = []
        fetch_error_code = ""
        for page in range(1, 3):
            prospects, total, err = _snov.search_prospects(domain, page=page)
            if err:
                fetch_error_code = err
                log_event(logger, "contact_fetch_prospects_error", domain=domain, page=page, err=err)
                break
            all_prospects.extend(prospects)
            if len(all_prospects) >= total or len(prospects) == 0:
                break

        if not all_prospects and fetch_error_code:
            return ContactProviderFetchResult(
                contacts=[],
                title_matched_count=0,
                error_code=fetch_error_code,
                error_message=f"Snov prospects failed: {fetch_error_code}",
            )

        contacts_to_write: list[dict[str, Any]] = []
        title_matched_count = 0
        for prospect in all_prospects:
            first_name = str(prospect.get("first_name") or "").strip()
            last_name = str(prospect.get("last_name") or "").strip()
            title = str(prospect.get("position") or "").strip()
            linkedin_url = str(prospect.get("source_page") or "").strip() or None
            search_emails_url = str(prospect.get("search_emails_start") or "")
            prospect_hash = search_emails_url.rstrip("/").rsplit("/", 1)[-1] if search_emails_url else ""
            title_matched = match_title(title, include_rules, exclude_words) if include_rules else False
            if title_matched:
                title_matched_count += 1

            contact_entry: dict[str, Any] = {
                "first_name": first_name,
                "last_name": last_name,
                "title": title or None,
                "title_match": title_matched,
                "linkedin_url": linkedin_url,
                "email": None,
                "provider_email_status": None,
                "verification_status": "unverified",
                "snov_confidence": None,
                "snov_prospect_raw": prospect,
                "apollo_prospect_raw": None,
                "snov_email_raw": None,
            }
            if title_matched and prospect_hash:
                emails, email_err = _snov.search_prospect_email(prospect_hash)
                if email_err:
                    return ContactProviderFetchResult(
                        contacts=[],
                        title_matched_count=title_matched_count,
                        error_code=email_err,
                        error_message=f"Snov email search failed: {email_err}",
                    )
                if emails:
                    best = emails[0]
                    contact_entry["email"] = str(best.get("email") or "").strip() or None
                    contact_entry["provider_email_status"] = str(best.get("smtp_status") or "unknown").lower()
                    contact_entry["snov_email_raw"] = emails

            if title_matched and not contact_entry["email"] and first_name and last_name:
                finder_emails, finder_err = _snov.find_email_by_name(first_name, last_name, domain)
                if finder_err:
                    return ContactProviderFetchResult(
                        contacts=[],
                        title_matched_count=title_matched_count,
                        error_code=finder_err,
                        error_message=f"Snov email finder failed: {finder_err}",
                    )
                if finder_emails:
                    best = finder_emails[0]
                    contact_entry["email"] = str(best.get("email") or "").strip() or None
                    contact_entry["provider_email_status"] = str(best.get("smtp_status") or "unknown").lower()
                    contact_entry["snov_email_raw"] = finder_emails

            contacts_to_write.append(contact_entry)

        log_event(
            logger,
            "contact_fetch_done",
            domain=domain,
            contacts=len(contacts_to_write),
            title_matched=title_matched_count,
        )
        return ContactProviderFetchResult(
            contacts=contacts_to_write,
            title_matched_count=title_matched_count,
        )

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
