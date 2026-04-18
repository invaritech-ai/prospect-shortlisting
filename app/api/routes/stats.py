"""Read-only pipeline stats: counts, averages, ETA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, literal_column
from sqlmodel import Session, col, func, select

from app.db.session import get_session
from app.models import AnalysisJob, Company, ContactFetchJob, ContactVerifyJob, ProspectContact, ScrapeJob
from app.models.pipeline import AnalysisJobState, ContactFetchJobState, ContactVerifyJobState


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


def _scrape_stats(session: Session, upload_id: UUID | None = None) -> PipelineStageStats:
    """Count per unique normalized_url using the latest (most recent) job only.

    This prevents inflated totals when scrape-all is run multiple times.
    Active (non-terminal) jobs always take priority: if a URL has a running or
    queued job, that is the one that counts, regardless of older terminal rows.
    """
    now = _utcnow()
    stuck_cutoff = now - timedelta(minutes=SCRAPE_RUNNING_STUCK_MINUTES)

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
    if upload_id:
        latest_stmt = latest_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(col(Company.upload_id) == upload_id)
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

    total = row.total or 0
    completed = row.completed or 0
    site_unavailable = row.site_unavailable or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0

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
        .order_by(col(ScrapeJob.updated_at).desc())
        .limit(_SAMPLE_SIZE)
    )
    if upload_id:
        recent_stmt = recent_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(col(Company.upload_id) == upload_id)
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
    )
    if upload_id:
        finished_window_stmt = finished_window_stmt.where(
            col(ScrapeJob.normalized_url).in_(
                select(Company.normalized_url).where(col(Company.upload_id) == upload_id)
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


def _analysis_stats(session: Session, upload_id: UUID | None = None) -> PipelineStageStats:
    now = _utcnow()

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
    row = session.exec(base).one()

    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0

    recent_stmt = (
        select(AnalysisJob.started_at, AnalysisJob.finished_at)
        .where(col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED)
        .order_by(col(AnalysisJob.finished_at).desc())
        .limit(_SAMPLE_SIZE)
    )
    if upload_id:
        recent_stmt = recent_stmt.where(col(AnalysisJob.upload_id) == upload_id)
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


def _contact_fetch_stats(session: Session, upload_id: UUID | None = None) -> PipelineStageStats:
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
    if upload_id:
        base = base.join(Company, col(Company.id) == col(ContactFetchJob.company_id)).where(col(Company.upload_id) == upload_id)
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


def _validation_stats(session: Session, upload_id: UUID | None = None) -> PipelineStageStats:
    base_stmt = select(ContactVerifyJob)
    if upload_id is not None:
        company_contact_ids = set(
            str(contact_id)
            for contact_id in session.exec(
                select(ProspectContact.id)
                .join(Company, col(Company.id) == col(ProspectContact.company_id))
                .where(col(Company.upload_id) == upload_id)
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
        ).select_from(ContactVerifyJob)
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


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    session: Session = Depends(get_session),
    upload_id: UUID | None = Query(default=None),
) -> StatsResponse:
    return StatsResponse(
        scrape=_scrape_stats(session, upload_id=upload_id),
        analysis=_analysis_stats(session, upload_id=upload_id),
        contact_fetch=_contact_fetch_stats(session, upload_id=upload_id),
        validation=_validation_stats(session, upload_id=upload_id),
        costs={"currency": "USD", "window_days": 30, "totals": _cost_totals().model_dump(mode="json")},
        as_of=_utcnow(),
    )


@router.get("/stats/costs", response_model=CostStatsResponse)
def get_cost_stats(
    session: Session = Depends(get_session),
    window_days: int = Query(default=30, ge=1, le=365),
    upload_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CostStatsResponse:
    window_cutoff = _utcnow() - timedelta(days=window_days)
    statement = select(Company.id, Company.domain).order_by(col(Company.domain).asc())
    statement = statement.where(col(Company.created_at) >= window_cutoff)
    if upload_id:
        statement = statement.where(col(Company.upload_id) == upload_id)

    rows = list(session.exec(statement.offset(offset).limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    total = session.exec(select(func.count()).select_from(statement.subquery())).one()
    items = [
        CostLineItem(
            company_id=str(company_id),
            domain=domain,
            scrape=None,
            analysis=None,
            contact_fetch=None,
            validation=None,
            overall=None,
        )
        for company_id, domain in page_rows
    ]
    return CostStatsResponse(
        currency="USD",
        window_days=window_days,
        totals=_cost_totals(),
        total=total or 0,
        has_more=has_more,
        limit=limit,
        offset=offset,
        items=items,
    )
