"""Operator queue-management endpoints: drain, reset stuck, mark failed, refresh runs."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, update
from sqlmodel import Session, col, func, select

from app.api.schemas.contacts import (
    ContactBacklogSummary,
    ContactBatchSummary,
    ContactFetchResult,
    ContactProviderBacklogItem,
    ContactReplayDeferredRequest,
    ContactReplayDeferredResult,
    ContactRetryFailedRequest,
    ContactRuntimeControlRead,
    ContactRuntimeControlUpdate,
)
from app.db.session import get_session
from app.models import (
    AnalysisJob,
    Campaign,
    Company,
    ContactFetchBatch,
    ContactFetchJob,
    ContactProviderAttempt,
    Run,
    ScrapeJob,
    Upload,
)
from app.models.pipeline import (
    AnalysisJobState,
    ContactFetchJobState,
    ContactProviderAttemptState,
    RunStatus,
)
from app.services.contact_queue_service import ContactQueueService
from app.services.contact_runtime_service import ContactRuntimeService
from app.services.pipeline_service import recompute_all_stages
from app.services.scrape_rules_store import load_rules_for_job


router = APIRouter(prefix="/v1", tags=["queue-admin"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class DrainQueueResult(BaseModel):
    cancelled_scrape_jobs: int
    cancelled_analysis_jobs: int


class ResetStuckResult(BaseModel):
    reset_count: int


class MarkFailedResult(BaseModel):
    marked_count: int


class ResetStuckAnalysisResult(BaseModel):
    reset_count: int


class MarkEmptyCompletedResult(BaseModel):
    marked_count: int


class RefreshRunStatusResult(BaseModel):
    refreshed_count: int


class RecomputePipelineStagesResult(BaseModel):
    refreshed_company_count: int
    refreshed_contact_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/queue/drain", response_model=DrainQueueResult)
def drain_queue(session: Session = Depends(get_session)) -> DrainQueueResult:
    """Cancel all queued work."""
    cancelled_scrape = session.exec(
        update(ScrapeJob)
        .where(col(ScrapeJob.status) == "created")
        .values(status="cancelled", terminal_state=True)
    ).rowcount  # type: ignore[union-attr]

    cancelled_analysis = session.exec(
        update(AnalysisJob)
        .where(
            col(AnalysisJob.terminal_state).is_(False)
            & (col(AnalysisJob.state) == AnalysisJobState.QUEUED)
        )
        .values(state=AnalysisJobState.DEAD, terminal_state=True)
    ).rowcount  # type: ignore[union-attr]

    session.commit()
    return DrainQueueResult(
        cancelled_scrape_jobs=cancelled_scrape or 0,
        cancelled_analysis_jobs=cancelled_analysis or 0,
    )


@router.post("/jobs/reset-stuck", response_model=ResetStuckResult)
def reset_stuck_jobs(session: Session = Depends(get_session)) -> ResetStuckResult:
    """Reset non-terminal scrape jobs stuck in running state and re-enqueue them."""
    from app.tasks.scrape import scrape_website

    stuck_ids = list(
        session.exec(
            select(ScrapeJob.id).where(
                col(ScrapeJob.terminal_state).is_(False)
                & (col(ScrapeJob.status) == "running")
            )
        ).all()
    )
    if stuck_ids:
        session.exec(
            update(ScrapeJob)
            .where(col(ScrapeJob.id).in_(stuck_ids))
            .values(status="created", lock_token=None, lock_expires_at=None, updated_at=_utcnow())
        )
        session.commit()
        for job_id in stuck_ids:
            scrape_website.delay(str(job_id), scrape_rules=load_rules_for_job(session=session, job_id=job_id))

    return ResetStuckResult(reset_count=len(stuck_ids))


@router.post("/jobs/mark-non-completed-failed", response_model=MarkFailedResult)
def mark_non_completed_failed(session: Session = Depends(get_session)) -> MarkFailedResult:
    """Mark all non-completed, non-failed scrape jobs as failed/terminal."""
    result = session.exec(
        update(ScrapeJob)
        .where(
            (col(ScrapeJob.status) != "completed")
            & (col(ScrapeJob.status) != "failed")
        )
        .values(status="failed", terminal_state=True)
    )
    session.commit()
    return MarkFailedResult(marked_count=result.rowcount or 0)  # type: ignore[union-attr]


@router.post("/analysis-jobs/reset-stuck", response_model=ResetStuckAnalysisResult)
def reset_stuck_analysis_jobs(session: Session = Depends(get_session)) -> ResetStuckAnalysisResult:
    """Reset analysis jobs stuck in RUNNING or QUEUED state and re-enqueue them."""
    from app.tasks.analysis import run_analysis_job

    stuck_ids = list(
        session.exec(
            select(AnalysisJob.id).where(
                col(AnalysisJob.terminal_state).is_(False)
                & col(AnalysisJob.state).in_([AnalysisJobState.RUNNING, AnalysisJobState.QUEUED])
            )
        ).all()
    )
    if stuck_ids:
        session.exec(
            update(AnalysisJob)
            .where(col(AnalysisJob.id).in_(stuck_ids))
            .values(
                state=AnalysisJobState.QUEUED,
                started_at=None,
                lock_token=None,
                lock_expires_at=None,
                updated_at=_utcnow(),
            )
        )
        session.commit()
        for job_id in stuck_ids:
            run_analysis_job.delay(str(job_id))

    return ResetStuckAnalysisResult(reset_count=len(stuck_ids))


@router.post("/jobs/mark-empty-completed-failed", response_model=MarkEmptyCompletedResult)
def mark_empty_completed_failed(session: Session = Depends(get_session)) -> MarkEmptyCompletedResult:
    """Mark scrape jobs that completed but produced zero markdown pages as failed."""
    result = session.exec(
        update(ScrapeJob)
        .where(
            (col(ScrapeJob.status) == "completed")
            & (col(ScrapeJob.markdown_pages_count) == 0)
        )
        .values(
            status="failed",
            terminal_state=True,
            last_error_code=func.coalesce(ScrapeJob.last_error_code, "no_markdown_produced"),
        )
    )
    session.commit()
    return MarkEmptyCompletedResult(marked_count=result.rowcount or 0)  # type: ignore[union-attr]


@router.post("/runs/refresh-status", response_model=RefreshRunStatusResult)
def refresh_run_statuses(session: Session = Depends(get_session)) -> RefreshRunStatusResult:
    """Recalculate status/progress for all non-completed runs based on current job states."""
    runs = list(
        session.exec(
            select(Run).where(col(Run.status).in_([RunStatus.RUNNING, RunStatus.CREATED]))
        )
    )
    if not runs:
        return RefreshRunStatusResult(refreshed_count=0)

    run_ids = [r.id for r in runs]
    agg_rows = session.exec(
        select(
            AnalysisJob.run_id,
            func.count(case((col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED, 1))).label("succeeded"),
            func.count(case((col(AnalysisJob.state).in_([AnalysisJobState.FAILED, AnalysisJobState.DEAD]), 1))).label("failed"),
            func.count(case((col(AnalysisJob.terminal_state).is_(True), 1))).label("terminal"),
        )
        .where(col(AnalysisJob.run_id).in_(run_ids))
        .group_by(AnalysisJob.run_id)
    ).all()

    counts = {row.run_id: row for row in agg_rows}
    now = datetime.now(timezone.utc)
    for run in runs:
        if run.total_jobs == 0:
            continue
        row = counts.get(run.id)
        succeeded = row.succeeded if row else 0
        failed = row.failed if row else 0
        terminal = row.terminal if row else 0

        run.completed_jobs = succeeded
        run.failed_jobs = failed
        is_done = terminal >= run.total_jobs
        if is_done:
            run.status = RunStatus.FAILED if failed > 0 else RunStatus.COMPLETED
            if not run.finished_at:
                run.finished_at = now
        else:
            run.status = RunStatus.RUNNING
        session.add(run)

    session.commit()
    return RefreshRunStatusResult(refreshed_count=len(runs))


@router.post("/pipeline/recompute-stages", response_model=RecomputePipelineStagesResult)
def recompute_pipeline_stages(session: Session = Depends(get_session)) -> RecomputePipelineStagesResult:
    company_changed, contact_changed = recompute_all_stages(session)
    session.commit()
    return RecomputePipelineStagesResult(
        refreshed_company_count=company_changed,
        refreshed_contact_count=contact_changed,
    )


@router.get("/contacts/admin/runtime-control", response_model=ContactRuntimeControlRead)
def get_contact_runtime_control(session: Session = Depends(get_session)) -> ContactRuntimeControlRead:
    control = ContactRuntimeService().get_or_create_control(session)
    return ContactRuntimeControlRead.model_validate(control, from_attributes=True)


@router.patch("/contacts/admin/runtime-control", response_model=ContactRuntimeControlRead)
def update_contact_runtime_control(
    payload: ContactRuntimeControlUpdate,
    session: Session = Depends(get_session),
) -> ContactRuntimeControlRead:
    control = ContactRuntimeService().update_control(
        session,
        auto_enqueue_enabled=payload.auto_enqueue_enabled,
        auto_enqueue_paused=payload.auto_enqueue_paused,
        auto_enqueue_max_batch_size=payload.auto_enqueue_max_batch_size,
        auto_enqueue_max_active_per_run=payload.auto_enqueue_max_active_per_run,
        dispatcher_batch_size=payload.dispatcher_batch_size,
    )
    if control.auto_enqueue_enabled and not control.auto_enqueue_paused:
        from app.tasks.contacts import dispatch_contact_fetch_jobs

        dispatch_contact_fetch_jobs.delay()
    return ContactRuntimeControlRead.model_validate(control, from_attributes=True)


@router.get("/contacts/admin/backlog", response_model=ContactBacklogSummary)
def get_contact_backlog(session: Session = Depends(get_session)) -> ContactBacklogSummary:
    job_counts = {
        str(state): int(count)
        for state, count in session.exec(
            select(ContactFetchJob.state, func.count())
            .group_by(ContactFetchJob.state)
        ).all()
    }
    attempt_counts = {
        str(state): int(count)
        for state, count in session.exec(
            select(ContactProviderAttempt.state, func.count())
            .group_by(ContactProviderAttempt.state)
        ).all()
    }

    provider_rollups: dict[str, ContactProviderBacklogItem] = {}
    for provider, state, last_error_code, count in session.exec(
        select(
            ContactProviderAttempt.provider,
            ContactProviderAttempt.state,
            ContactProviderAttempt.last_error_code,
            func.count(),
        )
        .group_by(
            ContactProviderAttempt.provider,
            ContactProviderAttempt.state,
            ContactProviderAttempt.last_error_code,
        )
    ).all():
        item = provider_rollups.setdefault(provider, ContactProviderBacklogItem(provider=provider))
        state_value = str(state)
        setattr(item, state_value, getattr(item, state_value) + int(count))
        if state_value in {
            ContactProviderAttemptState.QUEUED.value,
            ContactProviderAttemptState.DEFERRED.value,
        }:
            item.retryable += int(count)
        if last_error_code and "rate_limited" in last_error_code:
            item.rate_limited += int(count)

    recent_batches = [
        ContactBatchSummary(
            batch_id=batch.id,
            trigger_source=batch.trigger_source,
            requested_provider_mode=batch.requested_provider_mode,
            auto_enqueued=batch.auto_enqueued,
            state=str(batch.state),
            requested_count=batch.requested_count,
            queued_count=batch.queued_count,
            already_fetching_count=batch.already_fetching_count,
            last_error_code=batch.last_error_code,
            last_error_message=batch.last_error_message,
            created_at=batch.created_at,
            finished_at=batch.finished_at,
            updated_at=batch.updated_at,
        )
        for batch in session.exec(
            select(ContactFetchBatch)
            .order_by(col(ContactFetchBatch.created_at).desc())
            .limit(20)
        ).all()
    ]

    return ContactBacklogSummary(
        job_counts=job_counts,
        attempt_counts=attempt_counts,
        provider_attempt_counts=list(provider_rollups.values()),
        recent_batches=recent_batches,
    )


@router.post("/contacts/admin/retry-failed", response_model=ContactFetchResult)
def retry_failed_contact_companies(
    payload: ContactRetryFailedRequest,
    session: Session = Depends(get_session),
) -> ContactFetchResult:
    campaign = session.get(Campaign, payload.campaign_id)
    if campaign is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Campaign not found.")

    company_ids = list(dict.fromkeys(payload.company_ids or []))
    if company_ids:
        companies = list(
            session.exec(
                select(Company)
                .join(Upload, col(Upload.id) == col(Company.upload_id))
                .where(
                    col(Company.id).in_(company_ids),
                    col(Upload.campaign_id) == payload.campaign_id,
                )
            ).all()
        )
    else:
        failed_company_ids = list(
            session.exec(
                select(ContactFetchJob.company_id)
                .join(Company, col(Company.id) == col(ContactFetchJob.company_id))
                .join(Upload, col(Upload.id) == col(Company.upload_id))
                .where(
                    col(Upload.campaign_id) == payload.campaign_id,
                    col(ContactFetchJob.terminal_state).is_(True),
                    col(ContactFetchJob.state).in_([
                        ContactFetchJobState.FAILED,
                        ContactFetchJobState.DEAD,
                    ]),
                )
                .group_by(ContactFetchJob.company_id)
            ).all()
        )
        companies = (
            list(
                session.exec(
                    select(Company)
                    .where(col(Company.id).in_(failed_company_ids))
                    .order_by(col(Company.domain).asc())
                ).all()
            )
            if failed_company_ids
            else []
        )

    result = ContactQueueService().retry_failed_jobs(
        session=session,
        companies=companies,
        provider_mode=payload.provider_mode,
        campaign_id=payload.campaign_id,
    )
    return ContactFetchResult(
        requested_count=result.requested_count,
        queued_count=result.queued_count,
        already_fetching_count=result.already_fetching_count,
        queued_job_ids=result.queued_job_ids,
        batch_id=result.batch_id,
    )


@router.post("/contacts/admin/replay-deferred", response_model=ContactReplayDeferredResult)
def replay_deferred_contact_attempts(
    payload: ContactReplayDeferredRequest,
    session: Session = Depends(get_session),
) -> ContactReplayDeferredResult:
    attempts_stmt = (
        select(ContactProviderAttempt)
        .where(
            col(ContactProviderAttempt.terminal_state).is_(False),
            col(ContactProviderAttempt.state) == ContactProviderAttemptState.DEFERRED,
        )
        .order_by(col(ContactProviderAttempt.next_retry_at).asc(), col(ContactProviderAttempt.created_at).asc())
        .limit(payload.limit)
    )
    if payload.batch_id is not None:
        attempts_stmt = attempts_stmt.join(
            ContactFetchJob,
            col(ContactFetchJob.id) == col(ContactProviderAttempt.contact_fetch_job_id),
        ).where(col(ContactFetchJob.contact_fetch_batch_id) == payload.batch_id)
    if payload.provider != "both":
        attempts_stmt = attempts_stmt.where(col(ContactProviderAttempt.provider) == payload.provider)

    attempts = list(session.exec(attempts_stmt).all())
    if not attempts:
        return ContactReplayDeferredResult(replayed_attempt_count=0, scheduled_job_count=0)

    now = _utcnow()
    scheduled_job_ids: set[UUID] = set()
    for attempt in attempts:
        attempt.state = ContactProviderAttemptState.QUEUED
        attempt.deferred_reason = None
        attempt.next_retry_at = None
        attempt.updated_at = now
        session.add(attempt)

        job = session.get(ContactFetchJob, attempt.contact_fetch_job_id)
        if job is None or job.terminal_state:
            continue
        job.state = ContactFetchJobState.QUEUED
        job.lock_token = None
        job.lock_expires_at = None
        job.updated_at = now
        session.add(job)
        if job.id:
            scheduled_job_ids.add(job.id)

    session.commit()
    if scheduled_job_ids:
        from app.tasks.contacts import dispatch_contact_fetch_jobs

        dispatch_contact_fetch_jobs.delay()
    return ContactReplayDeferredResult(
        replayed_attempt_count=len(attempts),
        scheduled_job_count=len(scheduled_job_ids),
    )
