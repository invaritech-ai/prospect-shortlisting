from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import ContactRevealBatch, ContactRevealJob, DiscoveredContact, ProspectContact
from app.models.pipeline import ContactFetchBatchState, ContactFetchJobState, utcnow
from app.services.contact_runtime_service import ContactRuntimeService


@dataclass(frozen=True)
class ContactRevealEnqueueResult:
    selected_count: int
    queued_count: int
    already_revealing_count: int
    skipped_revealed_count: int
    queued_job_ids: list[UUID]
    batch_id: UUID | None = None


def discovered_group_key(contact: DiscoveredContact) -> str:
    linkedin = (contact.linkedin_url or "").strip().lower()
    if linkedin:
        return f"linkedin:{linkedin}"
    first_name = (contact.first_name or "").strip().lower()
    last_name = (contact.last_name or "").strip().lower()
    title = (contact.title or "").strip().lower()
    if first_name and last_name and title:
        return f"name_title:{first_name}|{last_name}|{title}"
    return f"provider:{contact.provider}:{contact.provider_person_id}"


class ContactRevealQueueService:
    def __init__(self) -> None:
        self._runtime = ContactRuntimeService()

    def enqueue_reveals(
        self,
        *,
        session: Session,
        campaign_id: UUID,
        discovered_contacts: list[DiscoveredContact],
        reveal_scope: str,
        trigger_source: str = "manual",
    ) -> ContactRevealEnqueueResult:
        if not discovered_contacts:
            return ContactRevealEnqueueResult(0, 0, 0, 0, [], None)

        control = self._runtime.get_or_create_control(session)
        if not control.reveal_enabled or control.reveal_paused:
            return ContactRevealEnqueueResult(len(discovered_contacts), 0, 0, 0, [], None)

        grouped: dict[tuple[UUID, str], list[DiscoveredContact]] = {}
        for contact in discovered_contacts:
            grouped.setdefault((contact.company_id, discovered_group_key(contact)), []).append(contact)

        batch = ContactRevealBatch(
            campaign_id=campaign_id,
            trigger_source=trigger_source,
            reveal_scope=reveal_scope,
            state=ContactFetchBatchState.QUEUED,
            requested_count=len(grouped),
            queued_count=0,
            already_revealing_count=0,
            skipped_revealed_count=0,
        )
        session.add(batch)
        session.flush()

        jobs_to_create: list[ContactRevealJob] = []
        already_revealing_count = 0
        skipped_revealed_count = 0
        for (company_id, group_key), members in grouped.items():
            if self._has_active_job(session=session, company_id=company_id, group_key=group_key):
                already_revealing_count += 1
                continue
            if self._already_revealed(session=session, company_id=company_id, members=members):
                skipped_revealed_count += 1
                continue
            requested_providers = self._requested_providers(members)
            if not requested_providers:
                skipped_revealed_count += 1
                continue
            jobs_to_create.append(
                ContactRevealJob(
                    contact_reveal_batch_id=batch.id,
                    company_id=company_id,
                    group_key=group_key,
                    discovered_contact_ids_json=[str(member.id) for member in members],
                    requested_providers_json=requested_providers,
                    state=ContactFetchJobState.QUEUED,
                    terminal_state=False,
                )
            )

        session.add_all(jobs_to_create)
        batch.queued_count = len(jobs_to_create)
        batch.already_revealing_count = already_revealing_count
        batch.skipped_revealed_count = skipped_revealed_count
        if not jobs_to_create:
            batch.state = ContactFetchBatchState.COMPLETED
            batch.finished_at = utcnow()
        batch.updated_at = utcnow()
        session.add(batch)
        session.commit()

        queued_job_ids = [job.id for job in jobs_to_create if job.id]
        self._dispatch_jobs(job_ids=queued_job_ids)
        return ContactRevealEnqueueResult(
            selected_count=len(discovered_contacts),
            queued_count=len(queued_job_ids),
            already_revealing_count=already_revealing_count,
            skipped_revealed_count=skipped_revealed_count,
            queued_job_ids=queued_job_ids,
            batch_id=batch.id,
        )

    def dispatch_queued_jobs(self, *, session: Session, limit: int | None = None) -> int:
        control = self._runtime.get_or_create_control(session)
        if not control.reveal_enabled or control.reveal_paused:
            return 0
        dispatch_limit = limit or control.reveal_dispatcher_batch_size
        if dispatch_limit <= 0:
            return 0
        jobs = list(
            session.exec(
                select(ContactRevealJob)
                .where(
                    col(ContactRevealJob.terminal_state).is_(False),
                    col(ContactRevealJob.state) == ContactFetchJobState.QUEUED,
                )
                .order_by(col(ContactRevealJob.created_at).asc())
                .limit(dispatch_limit)
            )
        )
        if not jobs:
            return 0
        queued_job_ids = [job.id for job in jobs if job.id]
        self._dispatch_jobs(job_ids=queued_job_ids)
        return len(queued_job_ids)

    @staticmethod
    def _requested_providers(contacts: Iterable[DiscoveredContact]) -> list[str]:
        providers = {contact.provider for contact in contacts}
        requested: list[str] = []
        if "apollo" in providers:
            requested.append("apollo")
        if "snov" in providers:
            requested.append("snov")
        return requested

    @staticmethod
    def _has_active_job(*, session: Session, company_id: UUID, group_key: str) -> bool:
        return session.exec(
            select(ContactRevealJob.id).where(
                col(ContactRevealJob.company_id) == company_id,
                col(ContactRevealJob.group_key) == group_key,
                col(ContactRevealJob.terminal_state).is_(False),
            )
        ).first() is not None

    @staticmethod
    def _already_revealed(
        *,
        session: Session,
        company_id: UUID,
        members: list[DiscoveredContact],
    ) -> bool:
        linkedin_candidates = [
            (member.linkedin_url or "").strip()
            for member in members
            if (member.linkedin_url or "").strip()
        ]
        if linkedin_candidates:
            existing = session.exec(
                select(ProspectContact.id).where(
                    col(ProspectContact.company_id) == company_id,
                    col(ProspectContact.linkedin_url).in_(linkedin_candidates),
                    col(ProspectContact.email).is_not(None),
                )
            ).first()
            if existing is not None:
                return True
        candidates = list(
            session.exec(
                select(ProspectContact).where(
                    col(ProspectContact.company_id) == company_id,
                    col(ProspectContact.email).is_not(None),
                )
            )
        )
        for member in members:
            first_name = (member.first_name or "").strip().lower()
            last_name = (member.last_name or "").strip().lower()
            title = (member.title or "").strip().lower()
            if not (first_name and last_name and title):
                continue
            for contact in candidates:
                if (contact.first_name or "").strip().lower() != first_name:
                    continue
                if (contact.last_name or "").strip().lower() != last_name:
                    continue
                if (contact.title or "").strip().lower() != title:
                    continue
                return True
        return False

    @staticmethod
    def _dispatch_jobs(*, job_ids: list[UUID]) -> None:
        if not job_ids:
            return
        from app.tasks.contacts import reveal_contact_emails

        for job_id in job_ids:
            reveal_contact_emails.delay(str(job_id))
