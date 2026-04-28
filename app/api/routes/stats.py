"""Read-only pipeline stats: counts, averages, ETA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, literal_column
from sqlmodel import Session, col, func, select

from app.db.session import get_session
from app.models import AiUsageEvent, AnalysisJob, Company, CompanyFeedback, ContactFetchJob, ContactVerifyJob, PipelineRun, ProspectContact, ScrapeJob, Upload
from app.models.pipeline import (
    AnalysisJobState,
    CompanyPipelineStage,
    ContactFetchJobState,
    ContactRevealBatch,
    ContactRevealJob,
    ContactVerifyJobState,
)
from app.api.schemas.upload import CompanyCounts
from app.services.company_service import latest_classification_subquery, latest_scrape_subquery


# A running scrape job that hasn't updated in > 35 min is considered stuck
# (matches the Beat reconciler threshold).
SCRAPE_RUNNING_STUCK_MINUTES = 35

router = APIRouter(prefix="/v1", tags=["stats"])

_SAMPLE_SIZE = 100  # recent completed jobs used to estimate average duration
_THROUGHPUT_WINDOW_MINUTES = 60  # look back this far to measure jobs/sec throughput


class PipelineStageStats(BaseModel):
    total: int
    completed: int
    failed: int
    site_unavailable: int
    running: int
    queued: int
    stuck_count: int
    pct_done: float
    avg_job_sec: float | None
    eta_seconds: float | None
    eta_at: datetime | None


class StatsResponse(BaseModel):
    scrape: PipelineStageStats
    analysis: PipelineStageStats
    contact_fetch: PipelineStageStats
    contact_reveal: PipelineStageStats
    validation: PipelineStageStats
    costs: dict[str, object] | None = None
    as_of: datetime


class StageCostTotals(BaseModel):
    scrape: float | None
    analysis: float | None
    contact_fetch: float | None
    validation: float | None
    overall: float | None


class CostLineItem(BaseModel):
    company_id: str
    domain: str
    scrape: float | None
    analysis: float | None
    contact_fetch: float | None
    validation: float | None
    overall: float | None


class CostStatsResponse(BaseModel):
    currency: str
    window_days: int
    totals: StageCostTotals
    total: int
    has_more: bool
    limit: int
    offset: int
    items: list[CostLineItem]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_campaign_upload_scope(
    *,
    session: Session,
    campaign_id: UUID,
    upload_id: UUID | None,
) -> None:
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    if upload_id is None:
        return
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    if upload.campaign_id != campaign_id:
        raise HTTPException(status_code=422, detail="upload_id is not assigned to the selected campaign.")


def _campaign_upload_ids_subquery(campaign_id: UUID):
    return select(Upload.id).where(col(Upload.campaign_id) == campaign_id)


def _campaign_company_count(
    session: Session,
    campaign_id: UUID,
    upload_id: UUID | None = None,
) -> int:
    """Total companies in campaign (or upload). Used as the stats denominator."""
    stmt = (
        select(func.count(Company.id))
        .join(Upload, Upload.id == Company.upload_id)
        .where(col(Upload.campaign_id) == campaign_id)
    )
    if upload_id:
        stmt = stmt.where(col(Company.upload_id) == upload_id)
    return session.exec(stmt).one() or 0


def _scrape_stats(
    session: Session,
    campaign_id: UUID,
    upload_id: UUID | None = None,
) -> PipelineStageStats:
    """Count per unique normalized_url using the latest (most recent) job only.

    This prevents inflated totals when scrape-all is run multiple times.
    Active (non-terminal) jobs always take priority: if a URL has a running or
    queued job, that is the one that counts, regardless of older terminal rows.
    """
    now = _utcnow()
    stuck_cutoff = now - timedelta(minutes=SCRAPE_RUNNING_STUCK_MINUTES)
    campaign_run_ids = select(PipelineRun.id).where(col(PipelineRun.campaign_id) == campaign_id)
    total_companies = _campaign_company_count(session, campaign_id, upload_id)

    # Subquery: pick one row per normalized_url.
    # Priority: non-terminal jobs first (they represent current work), then
    # most-recently-created terminal job.
    latest_stmt = select(
        ScrapeJob.id,
        ScrapeJob.status,
        ScrapeJob.terminal_state,
        ScrapeJob.updated_at,
        ScrapeJob.started_at,
        ScrapeJob.finished_at,
        func.row_number()
        .over(
            partition_by=ScrapeJob.normalized_url,
            order_by=(ScrapeJob.terminal_state.asc(), ScrapeJob.created_at.desc()),
        )
        .label("rn"),
    )
    latest_stmt = latest_stmt.where(col(ScrapeJob.pipeline_run_id).in_(campaign_run_ids))
    if upload_id:
        latest_stmt = latest_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(col(Company.upload_id) == upload_id)
            )
        )
    else:
        latest_stmt = latest_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(
                    col(Company.upload_id).in_(_campaign_upload_ids_subquery(campaign_id))
                )
            )
        )
    latest = (
        latest_stmt
        .subquery("latest")
    )
    latest_only = select(latest).where(literal_column("rn") == 1).subquery("lo")

    row = session.exec(
        select(
            func.count().label("total"),
            func.count(case((literal_column("lo.status") == "completed", 1))).label("completed"),
            func.count(case((literal_column("lo.status") == "site_unavailable", 1))).label("site_unavailable"),
            func.count(case((
                literal_column("lo.terminal_state").is_(True)
                & (literal_column("lo.status") != "completed")
                & (literal_column("lo.status") != "site_unavailable"),
                1,
            ))).label("failed"),
            func.count(case((
                literal_column("lo.terminal_state").is_(False)
                & (literal_column("lo.status") == "running"),
                1,
            ))).label("running"),
            func.count(case((literal_column("lo.status") == "created", 1))).label("queued"),
            func.count(case((
                literal_column("lo.terminal_state").is_(False)
                & (literal_column("lo.status") == "running")
                & (literal_column("lo.updated_at") < stuck_cutoff),
                1,
            ))).label("stuck_count"),
        ).select_from(latest_only)
    ).one()

    # job-based counts from the dedup window query
    completed = row.completed or 0
    site_unavailable = row.site_unavailable or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0
    # total = all companies in campaign (not just those with a job)
    total = total_companies

    # Prefer started_at/finished_at; fall back to created_at/updated_at for
    # jobs completed before the Celery migration added those timestamps.
    recent_stmt = (
        select(
            ScrapeJob.started_at,
            ScrapeJob.finished_at,
            ScrapeJob.created_at,
            ScrapeJob.updated_at,
        )
        .where(col(ScrapeJob.status) == "completed")
        .where(col(ScrapeJob.pipeline_run_id).in_(campaign_run_ids))
        .order_by(col(ScrapeJob.updated_at).desc())
        .limit(_SAMPLE_SIZE)
    )
    if upload_id:
        recent_stmt = recent_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(col(Company.upload_id) == upload_id)
            )
        )
    else:
        recent_stmt = recent_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(
                    col(Company.upload_id).in_(_campaign_upload_ids_subquery(campaign_id))
                )
            )
        )
    recent = list(session.exec(recent_stmt))
    avg_job_sec: float | None = None
    if recent:
        durations: list[float] = []
        for started, finished, created, updated in recent:
            s = started or created
            f = finished or updated
            if s and f and f > s:
                durations.append((f - s).total_seconds())
        if durations:
            avg_job_sec = sum(durations) / len(durations)

    remaining = queued + running
    pct_done = (completed + failed + site_unavailable) / total if total else 0.0

    # Throughput-based ETA: count jobs finished in the last N minutes,
    # compute jobs/sec, divide remaining by that rate.
    # This automatically reflects worker count and current site difficulty.
    throughput_window = now - timedelta(minutes=_THROUGHPUT_WINDOW_MINUTES)
    finished_window_stmt = select(func.count(ScrapeJob.id)).where(
        col(ScrapeJob.terminal_state).is_(True),
        col(ScrapeJob.finished_at) >= throughput_window,
        col(ScrapeJob.pipeline_run_id).in_(campaign_run_ids),
    )
    if upload_id:
        finished_window_stmt = finished_window_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(col(Company.upload_id) == upload_id)
            )
        )
    else:
        finished_window_stmt = finished_window_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(
                    col(Company.upload_id).in_(_campaign_upload_ids_subquery(campaign_id))
                )
            )
        )
    finished_in_window: int = session.exec(finished_window_stmt).one() or 0

    eta_seconds: float | None = None
    eta_at: datetime | None = None
    if finished_in_window > 0 and remaining > 0:
        jobs_per_sec = finished_in_window / (_THROUGHPUT_WINDOW_MINUTES * 60)
        eta_seconds = remaining / jobs_per_sec
        eta_at = datetime.fromtimestamp(now.timestamp() + eta_seconds, tz=timezone.utc)
    elif avg_job_sec and remaining > 0:
        # Fallback: no recent throughput data (pipeline just started)
        eta_seconds = remaining * avg_job_sec
        eta_at = datetime.fromtimestamp(now.timestamp() + eta_seconds, tz=timezone.utc)

    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        site_unavailable=site_unavailable,
        running=running,
        queued=queued,
        stuck_count=stuck_count,
        pct_done=round(pct_done * 100, 1),
        avg_job_sec=round(avg_job_sec, 1) if avg_job_sec else None,
        eta_seconds=round(eta_seconds, 0) if eta_seconds else None,
        eta_at=eta_at,
    )


def _analysis_stats(session: Session, campaign_id: UUID, upload_id: UUID | None = None) -> PipelineStageStats:
    now = _utcnow()
    total_companies = _campaign_company_count(session, campaign_id, upload_id)

    base = select(
        func.count().label("total"),
        func.count(case((col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED, 1))).label("completed"),
        func.count(case((
            col(AnalysisJob.state).in_([AnalysisJobState.FAILED, AnalysisJobState.DEAD]),
            1,
        ))).label("failed"),
        func.count(case((col(AnalysisJob.state) == AnalysisJobState.RUNNING, 1))).label("running"),
        func.count(case((col(AnalysisJob.state) == AnalysisJobState.QUEUED, 1))).label("queued"),
        func.count(case((
            col(AnalysisJob.terminal_state).is_(False)
            & (col(AnalysisJob.state) == AnalysisJobState.RUNNING)
            & col(AnalysisJob.lock_expires_at).is_not(None)
            & (col(AnalysisJob.lock_expires_at) < now),
            1,
        ))).label("stuck_count"),
    ).select_from(AnalysisJob)
    if upload_id:
        base = base.where(col(AnalysisJob.upload_id) == upload_id)
    else:
        base = base.where(col(AnalysisJob.upload_id).in_(_campaign_upload_ids_subquery(campaign_id)))
    row = session.exec(base).one()

    completed = row.completed or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0
    # total = all companies in campaign (not just those with an analysis job)
    total = total_companies

    recent_stmt = (
        select(AnalysisJob.started_at, AnalysisJob.finished_at)
        .where(col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED)
        .order_by(col(AnalysisJob.finished_at).desc())
        .limit(_SAMPLE_SIZE)
    )
    if upload_id:
        recent_stmt = recent_stmt.where(col(AnalysisJob.upload_id) == upload_id)
    else:
        recent_stmt = recent_stmt.where(col(AnalysisJob.upload_id).in_(_campaign_upload_ids_subquery(campaign_id)))
    recent = list(session.exec(recent_stmt))
    avg_job_sec = None
    if recent:
        durations = [(f - s).total_seconds() for s, f in recent if s and f and f > s]
        if durations:
            avg_job_sec = sum(durations) / len(durations)

    remaining = queued + running
    pct_done = (completed + failed) / total if total else 0.0

    throughput_window = now - timedelta(minutes=_THROUGHPUT_WINDOW_MINUTES)
    finished_stmt = select(func.count(AnalysisJob.id)).where(
        col(AnalysisJob.terminal_state).is_(True),
        col(AnalysisJob.finished_at) >= throughput_window,
    )
    if upload_id:
        finished_stmt = finished_stmt.where(col(AnalysisJob.upload_id) == upload_id)
    else:
        finished_stmt = finished_stmt.where(col(AnalysisJob.upload_id).in_(_campaign_upload_ids_subquery(campaign_id)))
    finished_in_window_analysis: int = session.exec(finished_stmt).one() or 0

    eta_seconds = None
    eta_at = None
    if finished_in_window_analysis > 0 and remaining > 0:
        jobs_per_sec = finished_in_window_analysis / (_THROUGHPUT_WINDOW_MINUTES * 60)
        eta_seconds = remaining / jobs_per_sec
        eta_at = datetime.fromtimestamp(now.timestamp() + eta_seconds, tz=timezone.utc)
    elif avg_job_sec and remaining > 0:
        eta_seconds = remaining * avg_job_sec
        eta_at = datetime.fromtimestamp(now.timestamp() + eta_seconds, tz=timezone.utc)

    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        site_unavailable=0,
        running=running,
        queued=queued,
        stuck_count=stuck_count,
        pct_done=round(pct_done * 100, 1),
        avg_job_sec=round(avg_job_sec, 1) if avg_job_sec else None,
        eta_seconds=round(eta_seconds, 0) if eta_seconds else None,
        eta_at=eta_at,
    )


def _contact_fetch_stats(session: Session, campaign_id: UUID, upload_id: UUID | None = None) -> PipelineStageStats:
    base = select(
        func.count().label("total"),
        func.count(case((col(ContactFetchJob.state) == ContactFetchJobState.SUCCEEDED, 1))).label("completed"),
        func.count(case((col(ContactFetchJob.state) == ContactFetchJobState.FAILED, 1))).label("failed"),
        func.count(case((col(ContactFetchJob.state) == ContactFetchJobState.RUNNING, 1))).label("running"),
        func.count(case((col(ContactFetchJob.state) == ContactFetchJobState.QUEUED, 1))).label("queued"),
        func.count(case((
            col(ContactFetchJob.terminal_state).is_(False)
            & (col(ContactFetchJob.state) == ContactFetchJobState.RUNNING)
            & col(ContactFetchJob.lock_expires_at).is_not(None)
            & (col(ContactFetchJob.lock_expires_at) < _utcnow()),
            1,
        ))).label("stuck_count"),
    ).select_from(ContactFetchJob)
    base = base.join(Company, col(Company.id) == col(ContactFetchJob.company_id)).where(
        col(Company.upload_id).in_(_campaign_upload_ids_subquery(campaign_id))
    )
    if upload_id:
        base = base.where(col(Company.upload_id) == upload_id)
    row = session.exec(base).one()
    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0
    pct_done = (completed + failed) / total if total else 0.0
    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        site_unavailable=0,
        running=running,
        queued=queued,
        stuck_count=stuck_count,
        pct_done=round(pct_done * 100, 1),
        avg_job_sec=None,
        eta_seconds=None,
        eta_at=None,
    )


def _contact_reveal_stats(session: Session, campaign_id: UUID, upload_id: UUID | None = None) -> PipelineStageStats:
    base = (
        select(
            func.count().label("total"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.SUCCEEDED, 1))).label("completed"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.FAILED, 1))).label("failed"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.RUNNING, 1))).label("running"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.QUEUED, 1))).label("queued"),
            func.count(case((
                col(ContactRevealJob.terminal_state).is_(False)
                & (col(ContactRevealJob.state) == ContactFetchJobState.RUNNING)
                & col(ContactRevealJob.lock_expires_at).is_not(None)
                & (col(ContactRevealJob.lock_expires_at) < _utcnow()),
                1,
            ))).label("stuck_count"),
        )
        .select_from(ContactRevealJob)
        .join(
            ContactRevealBatch,
            col(ContactRevealJob.contact_reveal_batch_id) == col(ContactRevealBatch.id),
        )
        .join(Company, col(Company.id) == col(ContactRevealJob.company_id))
        .where(col(ContactRevealBatch.campaign_id) == campaign_id)
    )
    if upload_id:
        base = base.where(col(Company.upload_id) == upload_id)
    row = session.exec(base).one()
    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0
    pct_done = (completed + failed) / total if total else 0.0
    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        site_unavailable=0,
        running=running,
        queued=queued,
        stuck_count=stuck_count,
        pct_done=round(pct_done * 100, 1),
        avg_job_sec=None,
        eta_seconds=None,
        eta_at=None,
    )


def _validation_stats(session: Session, campaign_id: UUID, upload_id: UUID | None = None) -> PipelineStageStats:
    base_stmt = select(ContactVerifyJob)
    company_scope = select(Company.id).where(col(Company.upload_id).in_(_campaign_upload_ids_subquery(campaign_id)))
    if upload_id is not None:
        company_scope = company_scope.where(col(Company.upload_id) == upload_id)
    company_contact_ids = set(
        str(contact_id)
        for contact_id in session.exec(
            select(ProspectContact.id)
            .join(Company, col(Company.id) == col(ProspectContact.company_id))
            .where(col(Company.id).in_(company_scope))
        ).all()
    )
    if not company_contact_ids:
        return PipelineStageStats(
            total=0,
            completed=0,
            failed=0,
            site_unavailable=0,
            running=0,
            queued=0,
            stuck_count=0,
            pct_done=0.0,
            avg_job_sec=None,
            eta_seconds=None,
            eta_at=None,
        )
    if upload_id is not None:
        company_contact_ids = set(
            str(contact_id)
            for contact_id in session.exec(
                select(ProspectContact.id)
                .join(Company, col(Company.id) == col(ProspectContact.company_id))
                .where(col(Company.upload_id) == upload_id)
            ).all()
        )

        matching_job_ids: list[UUID] = []
        for job in session.exec(base_stmt).all():
            contact_ids = job.contact_ids_json or []
            if any(contact_id in company_contact_ids for contact_id in contact_ids):
                matching_job_ids.append(job.id)
        if not matching_job_ids:
            return PipelineStageStats(
                total=0,
                completed=0,
                failed=0,
                site_unavailable=0,
                running=0,
                queued=0,
                stuck_count=0,
                pct_done=0.0,
                avg_job_sec=None,
                eta_seconds=None,
                eta_at=None,
            )
        stats_stmt = select(
            func.count().label("total"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.SUCCEEDED, 1))).label("completed"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.FAILED, 1))).label("failed"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.RUNNING, 1))).label("running"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.QUEUED, 1))).label("queued"),
            func.count(case((
                col(ContactVerifyJob.terminal_state).is_(False)
                & (col(ContactVerifyJob.state) == ContactVerifyJobState.RUNNING)
                & col(ContactVerifyJob.lock_expires_at).is_not(None)
                & (col(ContactVerifyJob.lock_expires_at) < _utcnow()),
                1,
            ))).label("stuck_count"),
        ).select_from(ContactVerifyJob).where(col(ContactVerifyJob.id).in_(matching_job_ids))
    else:
        matching_job_ids: list[UUID] = []
        for job in session.exec(base_stmt).all():
            contact_ids = job.contact_ids_json or []
            if any(contact_id in company_contact_ids for contact_id in contact_ids):
                matching_job_ids.append(job.id)
        if not matching_job_ids:
            return PipelineStageStats(
                total=0,
                completed=0,
                failed=0,
                site_unavailable=0,
                running=0,
                queued=0,
                stuck_count=0,
                pct_done=0.0,
                avg_job_sec=None,
                eta_seconds=None,
                eta_at=None,
            )
        stats_stmt = select(
            func.count().label("total"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.SUCCEEDED, 1))).label("completed"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.FAILED, 1))).label("failed"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.RUNNING, 1))).label("running"),
            func.count(case((col(ContactVerifyJob.state) == ContactVerifyJobState.QUEUED, 1))).label("queued"),
            func.count(case((
                col(ContactVerifyJob.terminal_state).is_(False)
                & (col(ContactVerifyJob.state) == ContactVerifyJobState.RUNNING)
                & col(ContactVerifyJob.lock_expires_at).is_not(None)
                & (col(ContactVerifyJob.lock_expires_at) < _utcnow()),
                1,
            ))).label("stuck_count"),
        ).select_from(ContactVerifyJob).where(col(ContactVerifyJob.id).in_(matching_job_ids))
    row = session.exec(stats_stmt).one()
    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0
    pct_done = (completed + failed) / total if total else 0.0
    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        site_unavailable=0,
        running=running,
        queued=queued,
        stuck_count=stuck_count,
        pct_done=round(pct_done * 100, 1),
        avg_job_sec=None,
        eta_seconds=None,
        eta_at=None,
    )


def _cost_totals() -> StageCostTotals:
    return StageCostTotals(
        scrape=None,
        analysis=None,
        contact_fetch=None,
        validation=None,
        overall=None,
    )


def _stage_cost_key(stage: str) -> str | None:
    if stage == "s1_scrape":
        return "scrape"
    if stage == "s2_analysis":
        return "analysis"
    if stage == "s3_contacts":
        return "contact_fetch"
    if stage == "s4_validation":
        return "validation"
    return None


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
) -> StatsResponse:
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)
    window_cutoff = _utcnow() - timedelta(days=30)
    totals_stmt = (
        select(
            AiUsageEvent.stage,
            func.coalesce(func.sum(AiUsageEvent.billed_cost_usd), 0.0).label("cost"),
        )
        .where(
            col(AiUsageEvent.campaign_id) == campaign_id,
            col(AiUsageEvent.created_at) >= window_cutoff,
        )
        .group_by(AiUsageEvent.stage)
    )
    if upload_id is not None:
        scoped_company_ids = select(Company.id).where(col(Company.upload_id) == upload_id)
        totals_stmt = totals_stmt.where(col(AiUsageEvent.company_id).in_(scoped_company_ids))
    totals_map = {"scrape": 0.0, "analysis": 0.0, "contact_fetch": 0.0, "validation": 0.0}
    for stage, cost in session.exec(totals_stmt).all():
        stage_key = _stage_cost_key(stage)
        if stage_key is not None:
            totals_map[stage_key] += float(cost or 0.0)
    return StatsResponse(
        scrape=_scrape_stats(session, campaign_id=campaign_id, upload_id=upload_id),
        analysis=_analysis_stats(session, campaign_id=campaign_id, upload_id=upload_id),
        contact_fetch=_contact_fetch_stats(session, campaign_id=campaign_id, upload_id=upload_id),
        contact_reveal=_contact_reveal_stats(session, campaign_id=campaign_id, upload_id=upload_id),
        validation=_validation_stats(session, campaign_id=campaign_id, upload_id=upload_id),
        costs={
            "currency": "USD",
            "window_days": 30,
            "totals": StageCostTotals(
                scrape=totals_map["scrape"],
                analysis=totals_map["analysis"],
                contact_fetch=totals_map["contact_fetch"],
                validation=totals_map["validation"],
                overall=totals_map["scrape"] + totals_map["analysis"] + totals_map["contact_fetch"] + totals_map["validation"],
            ).model_dump(mode="json"),
        },
        as_of=_utcnow(),
    )


@router.get("/stats/costs", response_model=CostStatsResponse)
def get_cost_stats(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    window_days: int = Query(default=30, ge=1, le=365),
    upload_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CostStatsResponse:
    if not isinstance(window_days, int):
        window_days = getattr(window_days, "default", 30)
    if not isinstance(upload_id, UUID):
        upload_id = getattr(upload_id, "default", None)
    _validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)
    window_cutoff = _utcnow() - timedelta(days=window_days)
    companies_stmt = (
        select(Company.id, Company.domain)
        .join(AiUsageEvent, col(AiUsageEvent.company_id) == col(Company.id))
        .where(
            col(AiUsageEvent.campaign_id) == campaign_id,
            col(AiUsageEvent.created_at) >= window_cutoff,
        )
        .group_by(Company.id, Company.domain)
        .order_by(col(Company.domain).asc())
    )
    if upload_id:
        companies_stmt = companies_stmt.where(col(Company.upload_id) == upload_id)

    rows = list(session.exec(companies_stmt.offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    total = session.exec(select(func.count()).select_from(companies_stmt.subquery())).one()
    page_company_ids = [company_id for company_id, _domain in page_rows]

    page_stage_rows: list[tuple[UUID, str, float]] = []
    if page_company_ids:
        page_stage_rows = list(
            session.exec(
                select(
                    AiUsageEvent.company_id,
                    AiUsageEvent.stage,
                    func.coalesce(func.sum(AiUsageEvent.billed_cost_usd), 0.0).label("cost"),
                )
                .where(
                    col(AiUsageEvent.campaign_id) == campaign_id,
                    col(AiUsageEvent.created_at) >= window_cutoff,
                    col(AiUsageEvent.company_id).in_(page_company_ids),
                )
                .group_by(AiUsageEvent.company_id, AiUsageEvent.stage)
            )
        )
    by_company: dict[UUID, dict[str, float]] = {}
    for company_id, stage, cost in page_stage_rows:
        bucket = by_company.setdefault(company_id, {"scrape": 0.0, "analysis": 0.0, "contact_fetch": 0.0, "validation": 0.0})
        stage_key = _stage_cost_key(stage)
        if stage_key is not None:
            bucket[stage_key] += float(cost or 0.0)

    total_stage_rows = list(
        session.exec(
            (
                select(
                    AiUsageEvent.stage,
                    func.coalesce(func.sum(AiUsageEvent.billed_cost_usd), 0.0).label("cost"),
                )
                .where(
                    col(AiUsageEvent.campaign_id) == campaign_id,
                    col(AiUsageEvent.created_at) >= window_cutoff,
                )
                .where(
                    col(AiUsageEvent.company_id).in_(
                        select(Company.id).where(col(Company.upload_id) == upload_id)
                    )
                )
                .group_by(AiUsageEvent.stage)
            )
            if upload_id is not None
            else select(
                AiUsageEvent.stage,
                func.coalesce(func.sum(AiUsageEvent.billed_cost_usd), 0.0).label("cost"),
            )
            .where(
                col(AiUsageEvent.campaign_id) == campaign_id,
                col(AiUsageEvent.created_at) >= window_cutoff,
            )
            .group_by(AiUsageEvent.stage)
        )
    )
    totals = {"scrape": 0.0, "analysis": 0.0, "contact_fetch": 0.0, "validation": 0.0}
    for stage, cost in total_stage_rows:
        stage_key = _stage_cost_key(stage)
        if stage_key is not None:
            totals[stage_key] += float(cost or 0.0)

    items: list[CostLineItem] = []
    for company_id, domain in page_rows:
        bucket = by_company.get(company_id, {"scrape": 0.0, "analysis": 0.0, "contact_fetch": 0.0, "validation": 0.0})
        overall = bucket["scrape"] + bucket["analysis"] + bucket["contact_fetch"] + bucket["validation"]
        items.append(
            CostLineItem(
                company_id=str(company_id),
                domain=domain,
                scrape=bucket["scrape"],
                analysis=bucket["analysis"],
                contact_fetch=bucket["contact_fetch"],
                validation=bucket["validation"],
                overall=overall,
            )
        )
    return CostStatsResponse(
        currency="USD",
        window_days=window_days,
        totals=StageCostTotals(
            scrape=totals["scrape"],
            analysis=totals["analysis"],
            contact_fetch=totals["contact_fetch"],
            validation=totals["validation"],
            overall=totals["scrape"] + totals["analysis"] + totals["contact_fetch"] + totals["validation"],
        ),
        total=total or 0,
        has_more=has_more,
        limit=limit,
        offset=offset,
        items=items,
    )


# ---------------------------------------------------------------------------
# Company counts (moved from companies.py)
# ---------------------------------------------------------------------------

@router.get("/companies/counts", response_model=CompanyCounts)
def get_company_counts(
    session: Session = Depends(get_session),
    campaign_id: UUID = Query(...),
    upload_id: UUID | None = Query(default=None),
) -> CompanyCounts:
    from app.services.company_service import validate_campaign_upload_scope
    validate_campaign_upload_scope(session=session, campaign_id=campaign_id, upload_id=upload_id)

    latest_classification = latest_classification_subquery()
    latest_scrape = latest_scrape_subquery()
    effective_decision = func.coalesce(CompanyFeedback.manual_label, latest_classification.c.predicted_label)
    decision_lower = func.lower(func.coalesce(effective_decision, ""))
    scrape_status = latest_scrape.c.status

    counts_stmt = (
        select(  # type: ignore[call-overload]
            func.count().label("total"),
            func.sum(case((latest_scrape.c.job_id.is_(None), 1), else_=0)).label("scrape_not_started"),
            func.sum(case((scrape_status.in_(["created", "running"]), 1), else_=0)).label("scrape_in_progress"),
            func.sum(case((scrape_status == "cancelled", 1), else_=0)).label("scrape_cancelled"),
            func.sum(case((scrape_status == "site_unavailable", 1), else_=0)).label("scrape_permanent_fail"),
            func.sum(case((scrape_status.in_(["failed", "step1_failed", "dead"]), 1), else_=0)).label("scrape_soft_fail"),
            func.sum(case((decision_lower == "", 1), else_=0)).label("unlabeled"),
            func.sum(case((decision_lower == "possible", 1), else_=0)).label("possible"),
            func.sum(case((decision_lower == "unknown", 1), else_=0)).label("unknown"),
            func.sum(case((decision_lower == "crap", 1), else_=0)).label("crap"),
            func.sum(case((scrape_status == "completed", 1), else_=0)).label("scrape_done"),
            func.sum(case((latest_scrape.c.job_id.is_(None), 1), else_=0)).label("not_scraped"),
            func.sum(case((scrape_status.in_(["failed", "step1_failed", "dead"]), 1), else_=0)).label("scrape_failed"),
        )
        .select_from(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .outerjoin(latest_classification, latest_classification.c.company_id == col(Company.id))
        .outerjoin(latest_scrape, latest_scrape.c.normalized_url == col(Company.normalized_url))
        .outerjoin(CompanyFeedback, col(CompanyFeedback.company_id) == col(Company.id))
        .where(col(Upload.campaign_id) == campaign_id)
    )
    if upload_id is not None:
        counts_stmt = counts_stmt.where(col(Company.upload_id) == upload_id)
    row = session.exec(counts_stmt).one()  # type: ignore[call-overload]

    stage_stmt = (
        select(  # type: ignore[call-overload]
            func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.UPLOADED, 1), else_=0)).label("uploaded"),
            func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.SCRAPED, 1), else_=0)).label("scraped"),
            func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.CLASSIFIED, 1), else_=0)).label("classified"),
            func.sum(case((col(Company.pipeline_stage) == CompanyPipelineStage.CONTACT_READY, 1), else_=0)).label("contact_ready"),
        )
        .select_from(Company)
        .join(Upload, col(Upload.id) == col(Company.upload_id))
        .where(col(Upload.campaign_id) == campaign_id)
    )
    if upload_id is not None:
        stage_stmt = stage_stmt.where(col(Company.upload_id) == upload_id)
    stage_row = session.exec(stage_stmt).one()

    return CompanyCounts(
        total=row[0] or 0,
        scrape_not_started=row[1] or 0,
        scrape_in_progress=row[2] or 0,
        scrape_cancelled=row[3] or 0,
        scrape_permanent_fail=row[4] or 0,
        scrape_soft_fail=row[5] or 0,
        uploaded=stage_row[0] or 0,
        scraped=stage_row[1] or 0,
        classified=stage_row[2] or 0,
        contact_ready=stage_row[3] or 0,
        unlabeled=row[6] or 0,
        possible=row[7] or 0,
        unknown=row[8] or 0,
        crap=row[9] or 0,
        scrape_done=row[10] or 0,
        scrape_failed=row[12] or 0,
        not_scraped=row[11] or 0,
    )
