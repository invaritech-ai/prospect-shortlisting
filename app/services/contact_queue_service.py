from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import Company, ContactFetchBatch, ContactFetchJob, ContactProviderAttempt, DiscoveredContact
from app.models.pipeline import ContactFetchBatchState, ContactFetchJobState, coerce_utc_datetime, utcnow
from app.services.contact_runtime_service import ContactRuntimeService


ProviderMode = Literal["snov", "apollo", "both"]
DISCOVERY_PROVIDER_ORDER: tuple[str, str] = ("snov", "apollo")


@dataclass(frozen=True)
class ContactEnqueueResult:
    requested_count: int
    queued_count: int
    already_fetching_count: int
    queued_job_ids: list[UUID]
    reused_count: int = 0
    stale_reused_count: int = 0
    batch_id: UUID | None = None


class ContactQueueService:
    def __init__(self) -> None:
        self._runtime = ContactRuntimeService()

    def enqueue_fetches(
        self,
        *,
        session: Session,
        companies: list[Company],
        provider_mode: ProviderMode = "both",
        campaign_id: UUID | None = None,
        pipeline_run_id: UUID | None = None,
        trigger_source: str = "manual",
        auto_enqueued: bool = False,
        force_refresh: bool = False,
    ) -> ContactEnqueueResult:
        if not companies:
            return ContactEnqueueResult(0, 0, 0, [], 0, 0, None)

        control = self._runtime.get_or_create_control(session)
        if auto_enqueued and (not control.auto_enqueue_enabled or control.auto_enqueue_paused):
            return ContactEnqueueResult(len(companies), 0, 0, [], 0, 0, None)

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
            force_refresh=force_refresh,
            state=ContactFetchBatchState.PAUSED if auto_enqueued and control.auto_enqueue_paused else ContactFetchBatchState.QUEUED,
            requested_count=requested_count,
            queued_count=0,
            already_fetching_count=0,
            reused_count=0,
            stale_reused_count=0,
        )
        session.add(batch)
        session.flush()

        jobs_to_create: list[ContactFetchJob] = []
        already_fetching_count = 0
        reused_count = 0
        stale_reused_count = 0
        for company in companies:
            if company.id in active_by_company:
                already_fetching_count += 1
                continue
            providers_to_fetch, reused_stale = self._providers_to_fetch(
                session=session,
                company_id=company.id,
                requested_providers=requested_providers,
                force_refresh=force_refresh,
            )
            if not providers_to_fetch:
                reused_count += 1
                if reused_stale:
                    stale_reused_count += 1
                continue
            jobs_to_create.append(
                ContactFetchJob(
                    company_id=company.id,
                    contact_fetch_batch_id=batch.id,
                    pipeline_run_id=pipeline_run_id,
                    provider=providers_to_fetch[0],
                    requested_providers_json=providers_to_fetch,
                    auto_enqueued=auto_enqueued,
                    state=ContactFetchJobState.QUEUED,
                    terminal_state=False,
                )
            )

        session.add_all(jobs_to_create)
        batch.queued_count = len(jobs_to_create)
        batch.already_fetching_count = already_fetching_count
        batch.reused_count = reused_count
        batch.stale_reused_count = stale_reused_count
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
            reused_count=reused_count,
            stale_reused_count=stale_reused_count,
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
            force_refresh=True,
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
            batch.state = (
                ContactFetchBatchState.COMPLETED
                if (batch.reused_count or 0) > 0 or batch.requested_count == 0
                else ContactFetchBatchState.FAILED
            )
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
            return list(DISCOVERY_PROVIDER_ORDER)
        return [provider_mode]

    @staticmethod
    def _dispatch_job(job: ContactFetchJob) -> None:
        from app.tasks.contacts import fetch_contacts, fetch_contacts_apollo

        if (job.provider or "").strip().lower() == "apollo":
            fetch_contacts_apollo.delay(str(job.id))
        else:
            fetch_contacts.delay(str(job.id))

    def _providers_to_fetch(
        self,
        *,
        session: Session,
        company_id: UUID,
        requested_providers: list[str],
        force_refresh: bool,
    ) -> tuple[list[str], bool]:
        if force_refresh:
            return requested_providers, False

        freshness_cutoff = utcnow() - timedelta(days=max(1, int(settings.contact_discovery_freshness_days)))
        providers_to_fetch: list[str] = []
        reused_stale = False
        for provider in requested_providers:
            last_seen = session.exec(
                select(func.max(DiscoveredContact.last_seen_at)).where(
                    col(DiscoveredContact.company_id) == company_id,
                    col(DiscoveredContact.provider) == provider,
                )
            ).one()
            if last_seen is None:
                last_seen = session.exec(
                    select(func.max(ContactProviderAttempt.finished_at))
                    .join(ContactFetchJob, col(ContactFetchJob.id) == col(ContactProviderAttempt.contact_fetch_job_id))
                    .where(
                        col(ContactFetchJob.company_id) == company_id,
                        col(ContactProviderAttempt.provider) == provider,
                        col(ContactProviderAttempt.state) == "succeeded",
                    )
                ).one()
            if last_seen is None:
                providers_to_fetch.append(provider)
                continue
            last_seen = coerce_utc_datetime(last_seen)
            if last_seen < freshness_cutoff:
                reused_stale = True
        return providers_to_fetch, reused_stale

    @staticmethod
    def _dispatch_jobs() -> None:
        from app.tasks.contacts import dispatch_contact_fetch_jobs

        dispatch_contact_fetch_jobs.delay()
