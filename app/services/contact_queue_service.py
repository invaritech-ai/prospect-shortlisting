from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Company, ContactFetchBatch, ContactFetchJob
from app.models.pipeline import ContactFetchBatchState, ContactFetchJobState, utcnow
from app.services.contact_runtime_service import ContactRuntimeService


ProviderMode = Literal["snov", "apollo", "both"]


@dataclass(frozen=True)
class ContactEnqueueResult:
    requested_count: int
    queued_count: int
    already_fetching_count: int
    queued_job_ids: list[UUID]
    batch_id: UUID | None = None


class ContactQueueService:
    def __init__(self) -> None:
        self._runtime = ContactRuntimeService()

    def enqueue_fetches(
        self,
        *,
        session: Session,
        companies: list[Company],
        provider_mode: ProviderMode = "snov",
        campaign_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        trigger_source: str = "manual",
        auto_enqueued: bool = False,
    ) -> ContactEnqueueResult:
        if not companies:
            return ContactEnqueueResult(0, 0, 0, [], None)

        control = self._runtime.get_or_create_control(session)
        if auto_enqueued and (not control.auto_enqueue_enabled or control.auto_enqueue_paused):
            return ContactEnqueueResult(len(companies), 0, 0, [], None)

        requested_providers = self._requested_providers(provider_mode)
        requested_count = len(companies)
        company_ids = [company.id for company in companies]
        session.exec(
            select(Company.id).where(col(Company.id).in_(company_ids)).with_for_update()
        ).all()

        active_jobs = list(
            session.exec(
                select(ContactFetchJob).where(
                    col(ContactFetchJob.company_id).in_(company_ids),
                    col(ContactFetchJob.terminal_state).is_(False),
                )
            )
        )
        active_by_company = {
            active_job.company_id: active_job
            for active_job in active_jobs
            if active_job.company_id is not None
        }

        batch = ContactFetchBatch(
            campaign_id=campaign_id,
            pipeline_run_id=pipeline_run_id,
            trigger_source=trigger_source,
            requested_provider_mode=provider_mode,
            auto_enqueued=auto_enqueued,
            state=ContactFetchBatchState.PAUSED if auto_enqueued and control.auto_enqueue_paused else ContactFetchBatchState.QUEUED,
            requested_count=requested_count,
            queued_count=0,
            already_fetching_count=0,
        )
        session.add(batch)
        session.flush()

        jobs_to_create: list[ContactFetchJob] = []
        already_fetching_count = 0
        for company in companies:
            if company.id in active_by_company:
                already_fetching_count += 1
                continue
            jobs_to_create.append(
                ContactFetchJob(
                    company_id=company.id,
                    contact_fetch_batch_id=batch.id,
                    pipeline_run_id=pipeline_run_id,
                    provider=requested_providers[0],
                    next_provider=None,
                    requested_providers_json=requested_providers,
                    auto_enqueued=auto_enqueued,
                    state=ContactFetchJobState.QUEUED,
                    terminal_state=False,
                )
            )

        session.add_all(jobs_to_create)
        batch.queued_count = len(jobs_to_create)
        batch.already_fetching_count = already_fetching_count
        batch.updated_at = utcnow()
        session.add(batch)
        session.commit()

        queued_job_ids = [job.id for job in jobs_to_create if job.id]
        self._dispatch_jobs()
        return ContactEnqueueResult(
            requested_count=requested_count,
            queued_count=len(queued_job_ids),
            already_fetching_count=already_fetching_count,
            queued_job_ids=queued_job_ids,
            batch_id=batch.id,
        )

    def dispatch_queued_jobs(
        self,
        *,
        session: Session,
        limit: int | None = None,
    ) -> int:
        control = self._runtime.get_or_create_control(session)
        dispatch_limit = limit or control.dispatcher_batch_size
        if dispatch_limit <= 0:
            return 0

        queued_jobs = list(
            session.exec(
                select(ContactFetchJob)
                .where(
                    col(ContactFetchJob.terminal_state).is_(False),
                    col(ContactFetchJob.state) == ContactFetchJobState.QUEUED,
                )
                .order_by(col(ContactFetchJob.auto_enqueued).asc(), col(ContactFetchJob.created_at).asc())
                .limit(dispatch_limit * 4)
            )
        )
        if not queued_jobs:
            return 0

        active_counts: dict[UUID, int] = {}
        if control.auto_enqueue_max_active_per_run > 0:
            active_rows = list(
                session.exec(
                    select(ContactFetchJob.pipeline_run_id)
                    .where(
                        col(ContactFetchJob.terminal_state).is_(False),
                        col(ContactFetchJob.state) == ContactFetchJobState.RUNNING,
                        col(ContactFetchJob.pipeline_run_id).is_not(None),
                    )
                )
            )
            for run_id in active_rows:
                if run_id is None:
                    continue
                active_counts[run_id] = active_counts.get(run_id, 0) + 1

        dispatched = 0
        for job in queued_jobs:
            if dispatched >= dispatch_limit or not job.id:
                break
            if job.auto_enqueued and (not control.auto_enqueue_enabled or control.auto_enqueue_paused):
                continue
            if (
                job.auto_enqueued
                and job.pipeline_run_id is not None
                and active_counts.get(job.pipeline_run_id, 0) >= control.auto_enqueue_max_active_per_run
            ):
                continue
            self._dispatch_job(job)
            dispatched += 1
            if job.auto_enqueued and job.pipeline_run_id is not None:
                active_counts[job.pipeline_run_id] = active_counts.get(job.pipeline_run_id, 0) + 1

        return dispatched

    def retry_failed_jobs(
        self,
        *,
        session: Session,
        companies: list[Company],
        provider_mode: ProviderMode = "both",
        campaign_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
    ) -> ContactEnqueueResult:
        return self.enqueue_fetches(
            session=session,
            companies=companies,
            provider_mode=provider_mode,
            campaign_id=campaign_id,
            pipeline_run_id=pipeline_run_id,
            trigger_source="retry",
            auto_enqueued=False,
        )

    def refresh_batch_state(self, session: Session, *, batch_id: UUID | None) -> None:
        if batch_id is None:
            return
        batch = session.get(ContactFetchBatch, batch_id)
        if batch is None:
            return
        jobs = list(
            session.exec(
                select(ContactFetchJob).where(col(ContactFetchJob.contact_fetch_batch_id) == batch_id)
            )
        )
        first_error = next(
            (
                (job.last_error_code, job.last_error_message)
                for job in jobs
                if job.last_error_code
            ),
            (None, None),
        )
        if not jobs:
            batch.state = ContactFetchBatchState.FAILED
        elif all(job.terminal_state for job in jobs):
            if any(job.state == ContactFetchJobState.SUCCEEDED for job in jobs):
                batch.state = ContactFetchBatchState.COMPLETED
                batch.last_error_code = None
                batch.last_error_message = None
            else:
                batch.state = ContactFetchBatchState.FAILED
                batch.last_error_code = first_error[0]
                batch.last_error_message = first_error[1]
            batch.finished_at = utcnow()
        elif batch.auto_enqueued and self._runtime.get_or_create_control(session).auto_enqueue_paused:
            batch.state = ContactFetchBatchState.PAUSED
            batch.last_error_code = None
            batch.last_error_message = None
        elif any(job.state == ContactFetchJobState.RUNNING for job in jobs):
            batch.state = ContactFetchBatchState.RUNNING
            batch.last_error_code = None
            batch.last_error_message = None
        else:
            batch.state = ContactFetchBatchState.QUEUED
            batch.last_error_code = None
            batch.last_error_message = None
        batch.updated_at = utcnow()
        session.add(batch)

    @staticmethod
    def _requested_providers(provider_mode: ProviderMode) -> list[str]:
        if provider_mode == "both":
            return ["snov", "apollo"]
        return [provider_mode]

    @staticmethod
    def _dispatch_job(job: ContactFetchJob) -> None:
        from app.tasks.contacts import fetch_contacts, fetch_contacts_apollo

        if (job.provider or "").strip().lower() == "apollo":
            fetch_contacts_apollo.delay(str(job.id))
        else:
            fetch_contacts.delay(str(job.id))

    @staticmethod
    def _dispatch_jobs() -> None:
        from app.tasks.contacts import dispatch_contact_fetch_jobs

        dispatch_contact_fetch_jobs.delay()
