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

from sqlalchemy import func, or_
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.core.logging import log_event
from app.models import Company, ContactFetchJob, ProspectContact, ProspectContactEmail, TitleMatchRule
from app.models.pipeline import ContactFetchJobState
from app.services.pipeline_service import recompute_contact_stages
from app.services.pipeline_run_orchestrator import enqueue_s4_for_contact_success
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

class ContactService:
    def _dispatch_contact_task(self, *, provider: str, job_id: UUID) -> None:
        from app.tasks.contacts import fetch_contacts, fetch_contacts_apollo

        if provider == "apollo":
            fetch_contacts_apollo.delay(str(job_id))
        else:
            fetch_contacts.delay(str(job_id))

    def _prepare_next_provider_if_needed(
        self,
        *,
        session: Session,
        job: ContactFetchJob,
    ) -> tuple[bool, tuple[str, UUID] | None]:
        next_provider = (job.next_provider or "").strip().lower()
        if next_provider not in {"snov", "apollo"}:
            return False, None
        existing_active = session.exec(
            select(ContactFetchJob.id).where(
                col(ContactFetchJob.company_id) == job.company_id,
                col(ContactFetchJob.provider) == next_provider,
                col(ContactFetchJob.terminal_state).is_(False),
            )
        ).first()
        if existing_active:
            return True, None
        followup = ContactFetchJob(
            company_id=job.company_id,
            pipeline_run_id=job.pipeline_run_id,
            provider=next_provider,
            next_provider=None,
        )
        session.add(followup)
        session.flush()
        if followup.id:
            return True, (next_provider, followup.id)
        return False, None

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
            apollo_title_filter = (
                _extract_apollo_title_filter(session) if job_provider == "apollo" else []
            )
        # ── session closed ────────────────────────────────────────────────────

        all_prospects: list[dict] = []
        contacts_to_write: list[dict] = []
        fetch_error_code = ""
        contacts_written = 0
        title_matched_count = 0

        if job_provider == "apollo":
            for page in range(1, 4):
                prospects = _apollo.search_people(
                    domain,
                    page=page,
                    person_titles=apollo_title_filter if apollo_title_filter else None,
                )
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
                existing = _find_existing_contact(
                    session=session,
                    company_id=company_id,
                    contact_entry=c,
                )

                if existing:
                    existing.contact_fetch_job_id = job_id
                    existing.first_name = c["first_name"] or existing.first_name
                    existing.last_name = c["last_name"] or existing.last_name
                    existing.title = c["title"] or existing.title
                    existing.title_match = c["title_match"]
                    existing.linkedin_url = c["linkedin_url"] or existing.linkedin_url
                    existing.source = existing.source or job_provider
                    existing.provider_email_status = c["provider_email_status"] or existing.provider_email_status
                    existing.snov_confidence = c["snov_confidence"] or existing.snov_confidence
                    if c["snov_prospect_raw"] is not None:
                        existing.snov_prospect_raw = c["snov_prospect_raw"]
                    if c.get("apollo_prospect_raw") is not None:
                        existing.apollo_prospect_raw = c.get("apollo_prospect_raw")
                    if c["snov_email_raw"] is not None:
                        existing.snov_email_raw = c["snov_email_raw"]
                    if existing.email:
                        _upsert_contact_email(
                            session=session,
                            contact=existing,
                            email=existing.email,
                            source=existing.source,
                            provider_email_status=existing.provider_email_status,
                            set_primary_if_missing=False,
                        )
                    _upsert_contact_email(
                        session=session,
                        contact=existing,
                        email=c.get("email"),
                        source=job_provider,
                        provider_email_status=c.get("provider_email_status"),
                    )
                    existing.updated_at = utcnow()
                    session.add(existing)
                    contacts_written += 1
                else:
                    new_contact = ProspectContact(
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
                    )
                    session.add(new_contact)
                    session.flush()
                    _upsert_contact_email(
                        session=session,
                        contact=new_contact,
                        email=c.get("email"),
                        source=job_provider,
                        provider_email_status=c.get("provider_email_status"),
                    )
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
            has_followup, followup_task = self._prepare_next_provider_if_needed(session=session, job=job)
            session.add(job)
            recompute_contact_stages(session, company_ids=[company_id])
            session.commit()
            session.refresh(job)
            if followup_task is not None:
                provider_name, followup_job_id = followup_task
                self._dispatch_contact_task(provider=provider_name, job_id=followup_job_id)
            if not has_followup:
                enqueue_s4_for_contact_success(engine=engine, contact_fetch_job_id=job.id)
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
            has_followup, followup_task = self._prepare_next_provider_if_needed(session=session, job=job)
            session.add(job)
            session.commit()
            session.refresh(job)
            if followup_task is not None:
                provider_name, followup_job_id = followup_task
                self._dispatch_contact_task(provider=provider_name, job_id=followup_job_id)
            if not has_followup:
                enqueue_s4_for_contact_success(engine=engine, contact_fetch_job_id=job.id)
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
            has_followup = False
            followup_task: tuple[str, UUID] | None = None
            if job.terminal_state:
                has_followup, followup_task = self._prepare_next_provider_if_needed(session=session, job=job)
            session.add(job)
            session.commit()
            session.refresh(job)
            if followup_task is not None:
                provider_name, followup_job_id = followup_task
                self._dispatch_contact_task(provider=provider_name, job_id=followup_job_id)
            if has_followup:
                log_event(
                    logger,
                    "contact_fetch_followup_enqueued_after_failure",
                    job_id=str(job.id),
                    provider=job.provider,
                    next_provider=job.next_provider,
                )
            return job
