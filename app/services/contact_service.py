"""ContactFetchJob execution: CAS-claim, Snov.io/Apollo prospect fetch, write results.

Three-phase pattern (same as AnalysisService):
  Phase 1 — CAS-claim job + load company domain + load title rules (short DB session)
  Phase 2 — Provider API calls: fetch prospects → filter by title → fetch emails (no DB)
  Phase 3 — Upsert ProspectContact rows + mark job terminal (new short DB session)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models import Company, ContactFetchJob, ProspectContact, TitleMatchRule
from app.models.pipeline import ContactFetchJobState
from app.services.pipeline_service import recompute_contact_stages
from app.services.apollo_client import (
    ERR_APOLLO_AUTH_FAILED,
    ERR_APOLLO_CREDENTIALS_MISSING,
    ApolloClient,
)
from app.services.snov_client import (
    ERR_SNOV_AUTH_FAILED,
    ERR_SNOV_CREDENTIALS_MISSING,
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
    """
    if not title:
        return False
    lowered = _normalize_title(title.lower())
    normalized_excludes = [_normalize_title(word.strip()) for word in exclude_words if word.strip()]
    if any(re.search(r"\b" + re.escape(word) + r"\b", lowered) for word in normalized_excludes):
        return False
    return any(
        all(re.search(r"\b" + re.escape(_normalize_title(kw)) + r"\b", lowered) for kw in keywords)
        for keywords in include_rules
    )


def load_title_rules(
    session: Session,
) -> tuple[list[list[str]], list[str]]:
    """Load include/exclude rules from DB. Returns (include_rules, exclude_words)."""
    rules = list(session.exec(select(TitleMatchRule)))
    include_rules: list[list[str]] = []
    exclude_words: list[str] = []
    for rule in rules:
        kws = [_normalize_title(k.strip()) for k in rule.keywords.split(",") if k.strip()]
        if rule.rule_type == "include" and kws:
            include_rules.append(kws)
        elif rule.rule_type == "exclude":
            exclude_words.extend(kws)
    return include_rules, exclude_words


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


# ── ContactService ────────────────────────────────────────────────────────────

class ContactService:
    def run_contact_fetch(self, *, engine: Any, job_id: UUID) -> ContactFetchJob | None:
        return self._run_contact_fetch(engine=engine, job_id=job_id, provider="snov")

    def run_apollo_fetch(self, *, engine: Any, job_id: UUID) -> ContactFetchJob | None:
        return self._run_contact_fetch(engine=engine, job_id=job_id, provider="apollo")

    def _run_contact_fetch(self, *, engine: Any, job_id: UUID, provider: str) -> ContactFetchJob | None:
        """Fetch contacts for a single ContactFetchJob.

        Returns the job object (terminal), or None if the CAS lock was lost.
        """
        now = utcnow()
        lock_token = str(uuid4())

        # ── Phase 1: CAS-claim + load context ────────────────────────────────
        with Session(engine) as session:
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
            if not job or job.lock_token != lock_token:
                log_event(logger, "contact_fetch_skipped_not_owner", job_id=str(job_id))
                return None

            job_provider = str(getattr(job, "provider", provider) or provider).lower()
            if job_provider not in {"snov", "apollo"}:
                return self._fail_job(
                    engine=engine, job_id=job_id, lock_token=lock_token,
                    error_code="contact_provider_invalid",
                    error_message=f"Unsupported contact provider: {job_provider}",
                    attempt_count=job.attempt_count,
                    max_attempts=1,
                )

        if not job.started_at:
            job.started_at = now
            session.add(job)
            session.commit()

            company = session.get(Company, job.company_id)
            if not company:
                return self._fail_job(
                    engine=engine, job_id=job_id, lock_token=lock_token,
                    error_code="contact_company_missing",
                    error_message="Company not found.",
                    attempt_count=job.attempt_count,
                    max_attempts=job.max_attempts,
                )

            domain = company.domain
            company_id = company.id
            include_rules, exclude_words = load_title_rules(session)
        # ── session closed ────────────────────────────────────────────────────

        all_prospects: list[dict] = []
        contacts_to_write: list[dict] = []
        fetch_error_code = ""
        contacts_written = 0
        title_matched_count = 0

        if job_provider == "apollo":
            for page in range(1, 4):
                prospects = _apollo.search_people(domain, page=page)
                apollo_err = _apollo.last_error_code
                if not prospects:
                    if apollo_err in _PERMANENT_ERROR_CODES:
                        return self._fail_job(
                            engine=engine, job_id=job_id, lock_token=lock_token,
                            error_code=apollo_err,
                            error_message=f"Apollo search failed: {apollo_err}",
                            attempt_count=1, max_attempts=1,
                        )
                    break
                all_prospects.extend(prospects)
                if len(prospects) < 100:
                    break

            if not all_prospects:
                if _apollo.last_error_code in _PERMANENT_ERROR_CODES:
                    return self._fail_job(
                        engine=engine, job_id=job_id, lock_token=lock_token,
                        error_code=_apollo.last_error_code,
                        error_message=f"Apollo search failed: {_apollo.last_error_code}",
                        attempt_count=1, max_attempts=1,
                    )
                if _apollo.last_error_code:
                    return self._fail_job(
                        engine=engine, job_id=job_id, lock_token=lock_token,
                        error_code=_apollo.last_error_code,
                        error_message=f"Apollo search failed: {_apollo.last_error_code}",
                        attempt_count=1, max_attempts=3,
                    )
                return self._complete_job(
                    engine=engine, job_id=job_id, lock_token=lock_token,
                    contacts_found=0, title_matched_count=0,
                )

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
                    continue

                email = str(person_details.get("email") or "").strip() or None
                if not email:
                    continue

                contact_entry = {
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
                contacts_to_write.append(contact_entry)
        else:
            # 2a. Free check — skip domains with 0 known emails
            count, err = _snov.get_domain_email_count(domain)
            if err in _PERMANENT_ERROR_CODES:
                return self._fail_job(
                    engine=engine, job_id=job_id, lock_token=lock_token,
                    error_code=err, error_message=f"Snov credentials error: {err}",
                    attempt_count=1, max_attempts=1,  # force terminal immediately
                )
            if err:
                return self._fail_job(
                    engine=engine, job_id=job_id, lock_token=lock_token,
                    error_code=err, error_message=f"Snov domain count failed: {err}",
                    attempt_count=1, max_attempts=3,
                )

            if count == 0:
                log_event(logger, "contact_fetch_no_emails", domain=domain)
                return self._complete_job(
                    engine=engine, job_id=job_id, lock_token=lock_token,
                    contacts_found=0, title_matched_count=0,
                )

            # 2b. Fetch prospects (paginate up to 2 pages = 40 prospects)
            for page in range(1, 3):
                prospects, total, err = _snov.search_prospects(domain, page=page)
                if err:
                    fetch_error_code = err
                    log_event(logger, "contact_fetch_prospects_error", domain=domain, page=page, err=err)
                    break
                all_prospects.extend(prospects)
                if len(all_prospects) >= total or len(prospects) == 0:
                    break

            if not all_prospects:
                if fetch_error_code in _PERMANENT_ERROR_CODES:
                    return self._fail_job(
                        engine=engine, job_id=job_id, lock_token=lock_token,
                        error_code=fetch_error_code, error_message=f"Snov prospects failed: {fetch_error_code}",
                        attempt_count=1, max_attempts=1,
                    )
                return self._complete_job(
                    engine=engine, job_id=job_id, lock_token=lock_token,
                    contacts_found=0, title_matched_count=0,
                )

            # 2c. Collect matched contacts and fetch their emails
            for prospect in all_prospects:
                first_name = str(prospect.get("first_name") or "").strip()
                last_name = str(prospect.get("last_name") or "").strip()
                title = str(prospect.get("position") or "").strip()
                linkedin_url = str(prospect.get("source_page") or "").strip() or None

                # Hash is embedded in the search_emails_start URL path, e.g.
                # ".../search-emails/start/abc123def456"
                search_emails_url = str(prospect.get("search_emails_start") or "")
                prospect_hash = search_emails_url.rstrip("/").rsplit("/", 1)[-1] if search_emails_url else ""

                title_matched = match_title(title, include_rules, exclude_words) if include_rules else False
                if title_matched:
                    title_matched_count += 1

                contact_entry: dict = {
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

                # 2d. Fetch email for title-matched prospects.
                #   Step 1: Snov database lookup (free if no result).
                #   Step 2: If empty, email finder by name+domain (1 credit if found).
                if title_matched and prospect_hash:
                    emails, email_err = _snov.search_prospect_email(prospect_hash)
                    if not email_err and emails:
                        best = emails[0]
                        contact_entry["email"] = str(best.get("email") or "").strip() or None
                        contact_entry["provider_email_status"] = str(best.get("smtp_status") or "unknown").lower()
                        contact_entry["snov_email_raw"] = emails

                # Fallback: guess email by name+domain if lookup returned nothing
                if title_matched and not contact_entry["email"] and first_name and last_name:
                    finder_emails, finder_err = _snov.find_email_by_name(first_name, last_name, domain)
                    if not finder_err and finder_emails:
                        best = finder_emails[0]
                        contact_entry["email"] = str(best.get("email") or "").strip() or None
                        contact_entry["provider_email_status"] = str(best.get("smtp_status") or "unknown").lower()
                        contact_entry["snov_email_raw"] = finder_emails
                        log_event(logger, "contact_email_found_by_name",
                                  domain=domain, name=f"{first_name} {last_name}",
                                  email=contact_entry["email"])

                contacts_to_write.append(contact_entry)
        log_event(logger, "contact_fetch_done", domain=domain,
                  contacts=len(contacts_to_write), title_matched=title_matched_count)

        # ── Phase 3: write results (new session) ─────────────────────────────
        with Session(engine) as session:
            job = session.get(ContactFetchJob, job_id)
            if not job or job.lock_token != lock_token:
                log_event(logger, "contact_fetch_results_skipped_not_owner", job_id=str(job_id))
                return None

            for c in contacts_to_write:
                # Upsert: if same company+email exists, update it
                existing: ProspectContact | None = None
                if c["email"]:
                    existing = session.exec(
                        select(ProspectContact).where(
                            col(ProspectContact.company_id) == company_id,
                            col(ProspectContact.email) == c["email"],
                        )
                    ).first()

                if existing:
                    if c.get("apollo_prospect_raw"):
                        continue
                    existing.contact_fetch_job_id = job_id
                    existing.first_name = c["first_name"]
                    existing.last_name = c["last_name"]
                    existing.title = c["title"]
                    existing.title_match = c["title_match"]
                    existing.linkedin_url = c["linkedin_url"]
                    existing.provider_email_status = c["provider_email_status"]
                    existing.snov_confidence = c["snov_confidence"]
                    if c["snov_prospect_raw"] is not None:
                        existing.snov_prospect_raw = c["snov_prospect_raw"]
                    if c.get("apollo_prospect_raw") is not None:
                        existing.apollo_prospect_raw = c.get("apollo_prospect_raw")
                    if c["snov_email_raw"] is not None:
                        existing.snov_email_raw = c["snov_email_raw"]
                    existing.updated_at = utcnow()
                    session.add(existing)
                    contacts_written += 1
                else:
                    session.add(ProspectContact(
                        company_id=company_id,
                        contact_fetch_job_id=job_id,
                        source=job_provider,
                        first_name=c["first_name"],
                        last_name=c["last_name"],
                        title=c["title"],
                        title_match=c["title_match"],
                        linkedin_url=c["linkedin_url"],
                        email=c["email"],
                        provider_email_status=c["provider_email_status"],
                        verification_status=c["verification_status"],
                        snov_confidence=c["snov_confidence"],
                        snov_prospect_raw=c["snov_prospect_raw"],
                        apollo_prospect_raw=c.get("apollo_prospect_raw"),
                        snov_email_raw=c["snov_email_raw"],
                    ))
                    contacts_written += 1

            now_finish = utcnow()
            job.state = ContactFetchJobState.SUCCEEDED
            job.terminal_state = True
            job.contacts_found = contacts_written
            job.title_matched_count = title_matched_count
            job.finished_at = now_finish
            job.updated_at = now_finish
            job.lock_token = None
            job.lock_expires_at = None
            session.add(job)
            recompute_contact_stages(session, company_ids=[company_id])
            session.commit()
            session.refresh(job)
            return job

    def _complete_job(
        self,
        *,
        engine: Any,
        job_id: UUID,
        lock_token: str,
        contacts_found: int,
        title_matched_count: int,
    ) -> ContactFetchJob | None:
        with Session(engine) as session:
            job = session.get(ContactFetchJob, job_id)
            if not job or job.lock_token != lock_token:
                return None
            now = utcnow()
            job.state = ContactFetchJobState.SUCCEEDED
            job.terminal_state = True
            job.contacts_found = contacts_found
            job.title_matched_count = title_matched_count
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
        error_code: str,
        error_message: str,
        lock_token: str,
        attempt_count: int,
        max_attempts: int,
    ) -> ContactFetchJob | None:
        is_permanent = error_code in _PERMANENT_ERROR_CODES
        attempts_exhausted = attempt_count >= max_attempts

        with Session(engine) as session:
            job = session.get(ContactFetchJob, job_id)
            if not job or job.lock_token != lock_token:
                log_event(logger, "contact_fail_skipped_not_owner", job_id=str(job_id))
                return job

            if is_permanent or attempts_exhausted:
                job.state = (
                    ContactFetchJobState.DEAD
                    if attempts_exhausted and not is_permanent
                    else ContactFetchJobState.FAILED
                )
                job.terminal_state = True
                job.finished_at = utcnow()
            else:
                # Transient failure — re-queue for retry
                job.state = ContactFetchJobState.QUEUED
                job.terminal_state = False
                job.lock_token = None
                job.lock_expires_at = None

            job.last_error_code = error_code
            job.last_error_message = error_message
            job.updated_at = utcnow()
            session.add(job)
            session.commit()
            session.refresh(job)
            return job
