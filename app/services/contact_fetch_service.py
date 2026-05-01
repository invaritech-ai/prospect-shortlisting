from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
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
    TitleMatchRule,
    Upload,
)
from app.models.pipeline import (
    ContactFetchBatchState,
    ContactFetchJobState,
    ContactProviderAttemptState,
)
from app.services.title_match_service import load_title_rules, match_title

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stable_id(first: str, last: str, domain: str) -> str:
    raw = f"{first.lower()}|{last.lower()}|{domain.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _snov_to_person(prospect: dict, domain: str) -> dict:
    pid = (
        str(prospect.get("id") or prospect.get("hash") or "").strip()
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
        """CAS-claim, run Snov then Apollo, upsert contacts, close job."""
        job_id = UUID(contact_fetch_job_id)
        lock_token = str(uuid4())
        now = _utcnow()

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

            # Extract plain values before session closes
            providers = list(job.requested_providers_json or ["snov", "apollo"])
            company_id_val = company.id
            company_domain = company.domain

            include_rules, exclude_words = load_title_rules(session, campaign_id=campaign_id)
            session.commit()

        total_found = 0
        total_matched = 0
        any_failure = False

        for seq_idx, provider in enumerate(providers):
            err = self._run_provider(
                engine=engine,
                job_id=job_id,
                company_id=company_id_val,
                company_domain=company_domain,
                provider=provider,
                seq_idx=seq_idx,
                include_rules=include_rules,
                exclude_words=exclude_words,
            )
            if err:
                any_failure = True
            else:
                with Session(engine) as session:
                    attempt = session.exec(
                        select(ContactProviderAttempt)
                        .where(
                            col(ContactProviderAttempt.contact_fetch_job_id) == job_id,
                            col(ContactProviderAttempt.provider) == provider,
                        )
                    ).first()
                    if attempt:
                        total_found += int(attempt.contacts_found or 0)
                        total_matched += int(attempt.title_matched_count or 0)

        final_state = ContactFetchJobState.FAILED if any_failure else ContactFetchJobState.SUCCEEDED
        with Session(engine) as session:
            job = session.get(ContactFetchJob, job_id)
            job.state = final_state
            job.terminal_state = True
            job.contacts_found = total_found
            job.title_matched_count = total_matched
            job.finished_at = _utcnow()
            job.updated_at = _utcnow()
            session.add(job)
            session.commit()

    def _run_provider(
        self,
        *,
        engine: Any,
        job_id: UUID,
        company_id: UUID,
        company_domain: str,
        provider: str,
        seq_idx: int,
        include_rules: list[list[str]],
        exclude_words: list[str],
    ) -> str:
        """Run one provider, upsert contacts. Returns error code or ''."""
        from app.services.apollo_client import ApolloClient
        from app.services.snov_client import SnovClient

        now = _utcnow()
        with Session(engine) as session:
            attempt = ContactProviderAttempt(
                contact_fetch_job_id=job_id,
                provider=provider,
                sequence_index=seq_idx,
                state=ContactProviderAttemptState.RUNNING,
                started_at=now,
            )
            session.add(attempt)
            session.commit()
            session.refresh(attempt)
            attempt_id = attempt.id

        people: list[dict] = []
        err = ""

        if provider == "snov":
            client = SnovClient()
            prospects, _total, err = client.search_prospects(company_domain)
            people = [_snov_to_person(p, company_domain) for p in prospects]
        elif provider == "apollo":
            client = ApolloClient()
            raw = client.search_people(company_domain)
            err = client.last_error_code
            people = [_apollo_to_person(p) for p in raw]
        else:
            err = f"unknown_provider_{provider}"

        contacts_found = 0
        title_matched = 0

        if not err:
            with Session(engine) as session:
                for person in people:
                    if not person.get("provider_person_id"):
                        continue
                    is_match = (
                        match_title(person.get("title") or "", include_rules, exclude_words)
                        if include_rules
                        else False
                    )
                    existing = session.exec(
                        select(Contact).where(
                            col(Contact.company_id) == company_id,
                            col(Contact.source_provider) == provider,
                            col(Contact.provider_person_id) == person["provider_person_id"],
                        )
                    ).first()
                    if existing:
                        existing.first_name = person.get("first_name", existing.first_name)
                        existing.last_name = person.get("last_name", existing.last_name)
                        existing.title = person.get("title", existing.title)
                        existing.linkedin_url = person.get("linkedin_url", existing.linkedin_url)
                        existing.provider_has_email = person.get("provider_has_email", existing.provider_has_email)
                        existing.title_match = is_match
                        existing.last_seen_at = _utcnow()
                        existing.updated_at = _utcnow()
                        existing.contact_fetch_job_id = job_id
                        session.add(existing)
                    else:
                        session.add(Contact(
                            company_id=company_id,
                            contact_fetch_job_id=job_id,
                            source_provider=provider,
                            provider_person_id=person["provider_person_id"],
                            first_name=person.get("first_name", ""),
                            last_name=person.get("last_name", ""),
                            title=person.get("title"),
                            linkedin_url=person.get("linkedin_url"),
                            provider_has_email=person.get("provider_has_email"),
                            raw_payload_json=person.get("raw_payload_json"),
                            title_match=is_match,
                        ))
                    contacts_found += 1
                    if is_match:
                        title_matched += 1
                session.commit()

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

        return err
