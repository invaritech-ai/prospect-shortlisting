from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from app.models import (
    Company,
    Contact,
    ContactFetchBatch,
    ContactFetchJob,
    ContactProviderAttempt,
    Upload,
)
from app.models.pipeline import (
    ContactFetchBatchState,
    ContactFetchJobState,
    ContactProviderAttemptState,
)
from app.services.title_match_service import (
    derive_apollo_filters,
    load_title_rules,
    match_title,
)


_JOB_LOCK_TTL = timedelta(hours=1)

logger = logging.getLogger(__name__)

_SNOV_MAX_PAGES = 50
_APOLLO_MAX_PAGES = 50


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(first: str, last: str, domain: str) -> str:
    raw = f"{first.lower()}|{last.lower()}|{domain.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _extract_snov_prospect_hash(prospect: dict) -> str:
    """Snov returns the prospect's real hash as the last path segment of
    `search_emails_start`. Extract it so reveal can call the correct endpoint.
    """
    url = str(prospect.get("search_emails_start") or "").strip()
    if not url:
        return ""
    return url.rsplit("/", 1)[-1].split("?")[0].strip()


def _snov_to_person(prospect: dict, domain: str) -> dict:
    snov_hash = _extract_snov_prospect_hash(prospect)
    pid = (
        snov_hash
        or str(prospect.get("id") or prospect.get("hash") or "").strip()
        or _stable_id(prospect.get("first_name", ""), prospect.get("last_name", ""), domain)
    )
    return {
        "provider_person_id": pid,
        "first_name": prospect.get("first_name") or "",
        "last_name": prospect.get("last_name") or "",
        "title": prospect.get("position") or prospect.get("title") or "",
        "provider_has_email": bool(prospect.get("search_emails_start")),
        "raw_payload_json": prospect,
    }


def _apollo_to_person(person: dict) -> dict:
    pid = str(person.get("id") or "").strip()
    if not pid:
        pid = _stable_id(person.get("first_name", ""), person.get("last_name", ""), "")
    return {
        "provider_person_id": pid,
        "first_name": person.get("first_name") or "",
        "last_name": person.get("last_name") or "",
        "title": person.get("title") or person.get("headline") or "",
        "linkedin_url": person.get("linkedin_url"),
        "provider_has_email": bool(person.get("email")),
        "raw_payload_json": person,
    }


def _dedupe_people(people: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for person in people:
        person_id = str(person.get("provider_person_id") or "").strip()
        if not person_id:
            continue
        by_id[person_id] = person
    return list(by_id.values())


def _active_job_for_company(session: Session, company_id: UUID) -> ContactFetchJob | None:
    return session.exec(
        select(ContactFetchJob)
        .where(
            col(ContactFetchJob.company_id) == company_id,
            col(ContactFetchJob.terminal_state).is_(False),
            col(ContactFetchJob.state).in_([ContactFetchJobState.QUEUED, ContactFetchJobState.RUNNING]),
        )
        .order_by(col(ContactFetchJob.created_at).desc())
    ).first()


class ContactFetchService:
    def enqueue(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        company_ids: list[UUID],
        force_refresh: bool = False,
    ) -> tuple[ContactFetchBatch, list[ContactFetchJob], int]:
        """Create a batch, find-or-create a job per company.

        Returns (batch, jobs, reused_count).
        Newly-created jobs have contact_fetch_batch_id == batch.id.
        Reused jobs retain their original batch_id.
        """
        
        batch = ContactFetchBatch(
            campaign_id=campaign_id,
            trigger_source="manual",
            requested_provider_mode="both",
            auto_enqueued=False,
            force_refresh=force_refresh,
            state=ContactFetchBatchState.QUEUED,
            requested_count=len(company_ids),
        )
        session.add(batch)
        session.flush()

        jobs: list[ContactFetchJob] = []
        reused = 0

        for company_id in company_ids:
            
            if not force_refresh:
                logger.info("enqueue_contact_fetch company_id=%s force_refresh=%s", company_id, force_refresh)
                existing = _active_job_for_company(session, company_id)
                if existing is not None:
                    reused += 1
                    jobs.append(existing)
                    continue

            job = ContactFetchJob(
                company_id=company_id,
                contact_fetch_batch_id=batch.id,
                provider="snov",
                requested_providers_json=["snov", "apollo"],
                auto_enqueued=False,
                state=ContactFetchJobState.QUEUED,
            )
            session.add(job)
            jobs.append(job)

        session.flush()

        batch.queued_count = sum(1 for j in jobs if j.contact_fetch_batch_id == batch.id)
        batch.already_fetching_count = reused
        batch.reused_count = reused
        session.add(batch)

        return batch, jobs, reused

    # ── Worker execution ──────────────────────────────────────────────────────

    def run_contact_fetch_job(self, *, engine: Any, contact_fetch_job_id: str) -> None:
        logger.info("[discover-check] run_contact_fetch_job CALLED contact_fetch_job_id=%s", contact_fetch_job_id)
        """Merged S3+S4 flow — Discover button handler.

        Contract (matches user-facing "Discover" semantics):
          - Fetch contacts from Apollo/Snov, **filter by campaign title rules
            only** — non-matching prospects are never saved.
          - Reveal email inline for every title-matched contact in the same job.
          - Upsert the matched contact row: when an email is found, update
            email + email_provider + email_confidence + provider_email_status
            + reveal_raw_json and flip pipeline_stage → email_revealed.

        Steps:
          1. CAS-claim the job.
          2. Short-circuit with 0 contacts if the campaign has no title rules
             (no contract to match against).
          3. Apollo first, with server-side title/seniority filter +
             local match_title() final filter (catches regex/AND rules).
          4. Snov fallback if Apollo errored or returned 0 matches.
          5. Inline reveal for every title-matched contact.
          6. Upsert by (company, provider, person_id) with name-based fallback
             to avoid duplicates when Snov's hash scheme drifts.
        """
        job_id = UUID(contact_fetch_job_id)
        lock_token = str(uuid4())
        now = _utcnow()
        logger.info(
            "[discover] run_contact_fetch_job START job_id=%s lock_token=%s now=%s",
            job_id, lock_token, now.isoformat(),
        )
        # Phase 1: CAS-claim + extract all data needed for subsequent phases
        with Session(engine) as session:
            updated = session.execute(
                sa_update(ContactFetchJob)
                .where(
                    col(ContactFetchJob.id) == job_id,
                    col(ContactFetchJob.terminal_state).is_(False),
                    col(ContactFetchJob.state).in_([ContactFetchJobState.QUEUED, ContactFetchJobState.RUNNING]),
                )
                .values(
                    state=ContactFetchJobState.RUNNING,
                    lock_token=lock_token,
                    lock_expires_at=now + _JOB_LOCK_TTL,
                    started_at=now,
                    updated_at=now,
                    attempt_count=ContactFetchJob.attempt_count + 1,
                )
                .returning(ContactFetchJob.id)
            )
            if not updated.fetchone():
                logger.warning("contact_fetch_job %s already claimed or terminal, skipping", job_id)
                return

            job = session.get(ContactFetchJob, job_id)
            company = session.get(Company, job.company_id)
            upload = session.get(Upload, company.upload_id)
            campaign_id = upload.campaign_id

            company_id_val = company.id
            company_domain = company.domain

            include_rules, exclude_words = load_title_rules(session, campaign_id=campaign_id)
            apollo_titles, apollo_seniorities = derive_apollo_filters(session, campaign_id=campaign_id)
            session.commit()

        # Phase 2a: short-circuit when there are no include rules. Without
        # rules there's nothing to match against, so we skip the provider calls
        # (no wasted credits) and mark the job succeeded with 0 contacts.
        if not include_rules:
            logger.warning(
                "contact_fetch_job %s: campaign %s has no title include rules — "
                "skipping discovery (no contracts to match against).",
                job_id, campaign_id,
            )
            with Session(engine) as session:
                job = session.get(ContactFetchJob, job_id)
                job.state = ContactFetchJobState.SUCCEEDED
                job.terminal_state = True
                job.contacts_found = 0
                job.title_matched_count = 0
                job.last_error_code = "no_title_rules"
                job.finished_at = _utcnow()
                job.updated_at = _utcnow()
                session.add(job)
                session.commit()
                batch_id = job.contact_fetch_batch_id
            if batch_id:
                self._maybe_finalize_batch(engine=engine, batch_id=batch_id)
            return

        # Phase 2b: Apollo (always tried first)
        apollo_matches, apollo_err = self._run_apollo(
            engine=engine,
            job_id=job_id,
            company_id=company_id_val,
            company_domain=company_domain,
            include_rules=include_rules,
            exclude_words=exclude_words,
            person_titles=apollo_titles,
            person_seniorities=apollo_seniorities,
            seq_idx=0,
        )

        # Phase 3: Snov fallback — only if Apollo errored OR returned 0 matches
        snov_matches: list[dict] = []
        snov_err = ""
        if apollo_err or not apollo_matches:
            snov_matches, snov_err = self._run_snov(
                engine=engine,
                job_id=job_id,
                company_id=company_id_val,
                company_domain=company_domain,
                include_rules=include_rules,
                exclude_words=exclude_words,
                seq_idx=1,
            )

        all_matches = apollo_matches + snov_matches

        # Phase 4: inline reveal + upsert (single transaction, batch for efficiency)
        revealed_count = self._reveal_and_upsert(
            engine=engine,
            job_id=job_id,
            company_id=company_id_val,
            company_domain=company_domain,
            matches=all_matches,
        )

        total_found = len(all_matches)
        total_matched = len(all_matches)
        any_failure = bool(apollo_err) and bool(snov_err or not snov_matches)

        final_state = (
            ContactFetchJobState.FAILED
            if any_failure and total_found == 0
            else ContactFetchJobState.SUCCEEDED
        )
        partial = bool(apollo_err) and total_found > 0
        _ = revealed_count  # currently unused; reserved for future telemetry
        with Session(engine) as session:
            job = session.get(ContactFetchJob, job_id)
            job.state = final_state
            job.terminal_state = True
            job.contacts_found = total_found
            job.title_matched_count = total_matched
            job.last_error_code = "partial_provider_failure" if partial else None
            job.finished_at = _utcnow()
            job.updated_at = _utcnow()
            session.add(job)
            session.commit()
            batch_id = job.contact_fetch_batch_id

        if batch_id:
            self._maybe_finalize_batch(engine=engine, batch_id=batch_id)

    def _open_attempt(
        self,
        *,
        engine: Any,
        job_id: UUID,
        provider: str,
        seq_idx: int,
    ) -> UUID:
        """Open (or reopen) a ContactProviderAttempt row, return its id."""
        now = _utcnow()
        with Session(engine) as session:
            attempt = session.exec(
                select(ContactProviderAttempt).where(
                    col(ContactProviderAttempt.contact_fetch_job_id) == job_id,
                    col(ContactProviderAttempt.provider) == provider,
                )
            ).first()
            if attempt is None:
                attempt = ContactProviderAttempt(
                    contact_fetch_job_id=job_id,
                    provider=provider,
                    sequence_index=seq_idx,
                    state=ContactProviderAttemptState.RUNNING,
                    started_at=now,
                )
                session.add(attempt)
            else:
                attempt.sequence_index = seq_idx
                attempt.state = ContactProviderAttemptState.RUNNING
                attempt.terminal_state = False
                attempt.started_at = now
                attempt.finished_at = None
                attempt.last_error_code = None
                attempt.last_error_message = None
                attempt.failure_reason = None
                attempt.deferred_reason = None
                attempt.updated_at = now
                session.add(attempt)
            session.commit()
            session.refresh(attempt)
            return attempt.id

    def _close_attempt(
        self,
        *,
        engine: Any,
        attempt_id: UUID,
        err: str,
        contacts_found: int,
        title_matched: int,
    ) -> None:
        final = ContactProviderAttemptState.SUCCEEDED if not err else ContactProviderAttemptState.FAILED
        with Session(engine) as session:
            attempt = session.get(ContactProviderAttempt, attempt_id)
            attempt.state = final
            attempt.terminal_state = True
            attempt.contacts_found = contacts_found
            attempt.title_matched_count = title_matched
            attempt.finished_at = _utcnow()
            attempt.updated_at = _utcnow()
            if err:
                attempt.last_error_code = err
            session.add(attempt)
            session.commit()

    def _run_apollo(
        self,
        *,
        engine: Any,
        job_id: UUID,
        company_id: UUID,
        company_domain: str,
        include_rules: list[list[str]],
        exclude_words: list[str],
        person_titles: list[str],
        person_seniorities: list[str],
        seq_idx: int,
    ) -> tuple[list[dict], str]:
        """Page through Apollo with server-side filters; return locally-matched people."""
        from app.services.apollo_client import ApolloClient

        attempt_id = self._open_attempt(engine=engine, job_id=job_id, provider="apollo", seq_idx=seq_idx)

        client = ApolloClient()
        raw_people: list[dict] = []
        err = ""
        page = 1
        while page <= _APOLLO_MAX_PAGES:
            raw = client.search_people(
                company_domain,
                page=page,
                person_titles=person_titles or None,
                person_seniorities=person_seniorities or None,
            )
            err = client.last_error_code
            if err:
                break
            if not raw:
                break
            raw_people.extend(raw)
            if len(raw) < 100:
                break
            page += 1

        people = _dedupe_people([_apollo_to_person(p) for p in raw_people])
        contacts_found = len(people)
        matches: list[dict] = []
        # Title rules are the contract: only matched contacts are saved + revealed.
        # When no include rules are configured the campaign cannot match anyone,
        # so we keep matches empty rather than falling back to "everyone".
        if not include_rules:
            logger.info(
                "contact_fetch apollo: no include rules for campaign — 0 matches; "
                "no contacts will be saved or revealed."
            )
        else:
            for p in people:
                if match_title(p.get("title") or "", include_rules, exclude_words):
                    matches.append({**p, "_provider": "apollo"})
        logger.info(
            "[discover] apollo_done domain=%s err=%r raw=%d unique=%d matched=%d",
            company_domain, err, len(raw_people), len(people), len(matches),
        )

        self._close_attempt(
            engine=engine,
            attempt_id=attempt_id,
            err=err,
            contacts_found=contacts_found,
            title_matched=len(matches),
        )
        _ = company_id  # reserved for per-attempt company linking if needed
        return matches, err

    def _run_snov(
        self,
        *,
        engine: Any,
        job_id: UUID,
        company_id: UUID,
        company_domain: str,
        include_rules: list[list[str]],
        exclude_words: list[str],
        seq_idx: int,
    ) -> tuple[list[dict], str]:
        """Page through Snov (no server-side title filter); return locally-matched people."""
        from app.services.snov_client import SnovClient

        attempt_id = self._open_attempt(engine=engine, job_id=job_id, provider="snov", seq_idx=seq_idx)

        client = SnovClient()
        all_prospects: list[dict] = []
        err = ""
        total_expected = 0
        page = 1
        while page <= _SNOV_MAX_PAGES:
            prospects, total, err = client.search_prospects(company_domain, page=page)
            if err:
                break
            if page == 1:
                total_expected = max(int(total or 0), 0)
            if not prospects:
                break
            all_prospects.extend(prospects)
            if total_expected and len(all_prospects) >= total_expected:
                break
            page += 1

        people = _dedupe_people([_snov_to_person(p, company_domain) for p in all_prospects])
        contacts_found = len(people)
        matches: list[dict] = []
        if not include_rules:
            logger.info(
                "contact_fetch snov: no include rules for campaign — 0 matches; "
                "no contacts will be saved or revealed."
            )
        else:
            for p in people:
                if match_title(p.get("title") or "", include_rules, exclude_words):
                    matches.append({**p, "_provider": "snov"})
        # Snapshot of matched people to verify pid extraction worked end-to-end.
        sample = [
            {
                "name": f"{m.get('first_name')} {m.get('last_name')}",
                "title": m.get("title"),
                "pid_len": len(str(m.get("provider_person_id") or "")),
                "provider_has_email": m.get("provider_has_email"),
            }
            for m in matches[:5]
        ]
        logger.info(
            "[discover] snov_done domain=%s err=%r raw=%d unique=%d matched=%d sample=%s",
            company_domain, err, len(all_prospects), len(people), len(matches), sample,
        )

        self._close_attempt(
            engine=engine,
            attempt_id=attempt_id,
            err=err,
            contacts_found=contacts_found,
            title_matched=len(matches),
        )
        _ = company_id
        return matches, err

    def _reveal_email_for(self, person: dict, company_domain: str) -> tuple[str, str | None, dict]:
        """Reveal a single person's email via the right provider.

        Returns (email, smtp_status, raw_payload). Empty email means reveal failed
        or returned nothing — caller stores the contact as fetched_no_email.
        """
        from app.services.contact_reveal import reveal_email_for_person

        provider = str(person.get("_provider") or "")
        pid = str(person.get("provider_person_id") or "")
        first = str(person.get("first_name") or "")
        last = str(person.get("last_name") or "")
        logger.info(
            "[discover] reveal_call provider=%s pid=%s name=%s %s domain=%s",
            provider, pid[:24] + ("..." if len(pid) > 24 else ""), first, last, company_domain,
        )
        result = reveal_email_for_person(
            provider=provider,
            person_id=pid,
            first_name=first,
            last_name=last,
            domain=company_domain,
        )
        logger.info(
            "[discover] reveal_result provider=%s pid=%s name=%s %s "
            "email=%r smtp=%s err=%r",
            provider, pid[:24] + ("..." if len(pid) > 24 else ""), first, last,
            result.email, result.smtp_status, result.error_code,
        )
        return result.email, result.smtp_status, result.raw or {}

    def _reveal_and_upsert(
        self,
        *,
        engine: Any,
        job_id: UUID,
        company_id: UUID,
        company_domain: str,
        matches: list[dict],
    ) -> int:
        """Reveal emails inline for every matched contact and upsert."""
        logger.info(
            "[discover] reveal_and_upsert START job_id=%s company_id=%s domain=%s matches=%d",
            job_id, company_id, company_domain, len(matches),
        )
        if not matches:
            logger.info("[discover] reveal_and_upsert: no matches, returning 0")
            return 0

        # Reveal phase — outside DB transaction (network calls).
        # Always attempt reveal: Apollo search results don't carry the unlocked
        # email (need /people/match), so gating on `provider_has_email` would
        # silently skip every Apollo contact.
        revealed = 0
        for person in matches:
            email, smtp_status, raw = self._reveal_email_for(person, company_domain)
            if email:
                person["_email"] = email
                person["_smtp_status"] = smtp_status
                person["_reveal_raw"] = raw
                revealed += 1
        logger.info(
            "[discover] reveal_phase_done job_id=%s revealed=%d/%d",
            job_id, revealed, len(matches),
        )

        # Upsert phase
        with Session(engine) as session:
            person_ids = [str(p.get("provider_person_id") or "").strip() for p in matches]
            person_ids = [pid for pid in person_ids if pid]
            existing_rows: list[Contact] = []
            if person_ids:
                # Group by provider so we hit the unique-key (company, provider, person_id) correctly.
                for provider in {p["_provider"] for p in matches}:
                    pids_for_provider = [
                        str(p.get("provider_person_id") or "").strip()
                        for p in matches
                        if p.get("_provider") == provider
                    ]
                    pids_for_provider = [pid for pid in pids_for_provider if pid]
                    if not pids_for_provider:
                        continue
                    existing_rows.extend(
                        session.exec(
                            select(Contact).where(
                                col(Contact.company_id) == company_id,
                                col(Contact.source_provider) == provider,
                                col(Contact.provider_person_id).in_(pids_for_provider),
                            )
                        )
                    )
            existing_by_key: dict[tuple[str, str], Contact] = {
                (c.source_provider, str(c.provider_person_id)): c for c in existing_rows
            }

            # Name-based fallback: older rows may have been written with a
            # different `provider_person_id` (Snov's hash extraction changed in
            # commit a9922fc). Without this fallback, re-running Discover would
            # insert a duplicate row for the same person. Build a (provider,
            # fn_lower, ln_lower) -> Contact map over all existing rows for this
            # company so we can match by name when the pid lookup misses.
            existing_by_name: dict[tuple[str, str, str], Contact] = {}
            providers_in_matches = {p["_provider"] for p in matches}
            if providers_in_matches:
                all_rows = list(
                    session.exec(
                        select(Contact).where(
                            col(Contact.company_id) == company_id,
                            col(Contact.source_provider).in_(providers_in_matches),
                        )
                    )
                )
                for r in all_rows:
                    fn = (r.first_name or "").strip().lower()
                    ln = (r.last_name or "").strip().lower()
                    if not fn or not ln:
                        continue
                    nkey = (r.source_provider, fn, ln)
                    # Prefer the row already revealed; otherwise the most recent
                    incumbent = existing_by_name.get(nkey)
                    if incumbent is None:
                        existing_by_name[nkey] = r
                    elif not incumbent.email and r.email:
                        existing_by_name[nkey] = r

            logger.info(
                "[discover] upsert_lookup job_id=%s existing_by_pid=%d existing_by_name=%d",
                job_id, len(existing_by_key), len(existing_by_name),
            )
            now = _utcnow()
            for person in matches:
                provider = person["_provider"]
                pid = str(person.get("provider_person_id") or "").strip()
                if not pid:
                    logger.warning(
                        "[discover] upsert_skip name=%s %s reason=empty_pid provider=%s",
                        person.get("first_name"), person.get("last_name"), provider,
                    )
                    continue
                email = person.get("_email") or ""
                smtp_status = person.get("_smtp_status")
                stage = "email_revealed" if email else "fetched_no_email"

                key = (provider, pid)
                existing = existing_by_key.get(key)
                match_path = "by_pid" if existing else ""
                if existing is None:
                    fn = (person.get("first_name") or "").strip().lower()
                    ln = (person.get("last_name") or "").strip().lower()
                    if fn and ln:
                        nkey = (provider, fn, ln)
                        existing = existing_by_name.pop(nkey, None)
                        if existing is not None:
                            match_path = "by_name"
                            # Migrate the stale row's pid to the new canonical
                            # value so future runs hit existing_by_key directly.
                            existing.provider_person_id = pid
                            existing_by_key[key] = existing
                if existing is None:
                    match_path = "new_insert"
                logger.info(
                    "[discover] upsert_resolve provider=%s name=%s %s pid=%s "
                    "email=%r match=%s stage=%s",
                    provider, person.get("first_name"), person.get("last_name"),
                    pid[:24] + ("..." if len(pid) > 24 else ""),
                    email, match_path, stage,
                )
                if existing:
                    existing.first_name = person.get("first_name", existing.first_name)
                    existing.last_name = person.get("last_name", existing.last_name)
                    existing.title = person.get("title", existing.title)
                    existing.linkedin_url = person.get("linkedin_url", existing.linkedin_url)
                    existing.provider_has_email = person.get("provider_has_email", existing.provider_has_email)
                    existing.title_match = True
                    existing.last_seen_at = now
                    existing.updated_at = now
                    existing.contact_fetch_job_id = job_id
                    if email:
                        existing.email = email
                        existing.email_provider = provider
                        existing.email_confidence = 1.0 if smtp_status == "valid" else (0.5 if smtp_status == "unknown" else 0.0)
                        existing.provider_email_status = smtp_status
                        existing.reveal_raw_json = person.get("_reveal_raw")
                        # Don't downgrade a contact already validated by S5
                        if existing.pipeline_stage != "campaign_ready":
                            existing.pipeline_stage = stage
                    else:
                        # Only push back to fetched_no_email if it isn't already further along
                        if existing.pipeline_stage in ("fetched", ""):
                            existing.pipeline_stage = stage
                    session.add(existing)
                else:
                    created = Contact(
                        company_id=company_id,
                        contact_fetch_job_id=job_id,
                        source_provider=provider,
                        provider_person_id=pid,
                        first_name=person.get("first_name", ""),
                        last_name=person.get("last_name", ""),
                        title=person.get("title"),
                        linkedin_url=person.get("linkedin_url"),
                        provider_has_email=person.get("provider_has_email"),
                        raw_payload_json=person.get("raw_payload_json"),
                        title_match=True,
                        pipeline_stage=stage,
                    )
                    if email:
                        created.email = email
                        created.email_provider = provider
                        created.email_confidence = 1.0 if smtp_status == "valid" else (0.5 if smtp_status == "unknown" else 0.0)
                        created.provider_email_status = smtp_status
                        created.reveal_raw_json = person.get("_reveal_raw")
                    session.add(created)
            try:
                session.commit()
                logger.info(
                    "[discover] upsert_committed job_id=%s revealed=%d/%d",
                    job_id, revealed, len(matches),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "[discover] upsert_commit_failed job_id=%s error=%s",
                    job_id, exc,
                )
                raise

        return revealed

    def _maybe_finalize_batch(self, *, engine: Any, batch_id: UUID) -> None:
        """If every job in this batch is terminal, mark the batch succeeded/failed."""
        from sqlalchemy import func as _func

        with Session(engine) as session:
            pending = session.exec(
                select(_func.count(ContactFetchJob.id))
                .where(
                    col(ContactFetchJob.contact_fetch_batch_id) == batch_id,
                    col(ContactFetchJob.terminal_state).is_(False),
                )
            ).one()

            if pending > 0:
                return

            any_failed = session.exec(
                select(_func.count(ContactFetchJob.id))
                .where(
                    col(ContactFetchJob.contact_fetch_batch_id) == batch_id,
                    col(ContactFetchJob.state) == ContactFetchJobState.FAILED,
                )
            ).one()

            batch = session.get(ContactFetchBatch, batch_id)
            if batch is None:
                return
            batch.state = (
                ContactFetchBatchState.FAILED if any_failed else ContactFetchBatchState.SUCCEEDED
            )
            batch.finished_at = _utcnow()
            batch.updated_at = _utcnow()
            session.add(batch)
            session.commit()
