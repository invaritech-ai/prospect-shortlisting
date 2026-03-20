"""Read-only pipeline stats: counts, averages, ETA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, literal_column
from sqlmodel import Session, col, func, select

from app.db.session import get_session
from app.models import AnalysisJob, ScrapeJob
from app.models.pipeline import AnalysisJobState


# A running scrape job that hasn't updated in > 35 min is considered stuck
# (matches the Beat reconciler threshold).
SCRAPE_RUNNING_STUCK_MINUTES = 35

router = APIRouter(prefix="/v1", tags=["stats"])

_SAMPLE_SIZE = 100  # recent completed jobs used to estimate average duration


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
    as_of: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _scrape_stats(session: Session) -> PipelineStageStats:
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
    latest = (
        select(
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
    recent = list(
        session.exec(
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
    )
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
    eta_seconds: float | None = None
    eta_at: datetime | None = None
    if avg_job_sec and remaining > 0:
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


def _analysis_stats(session: Session) -> PipelineStageStats:
    now = _utcnow()

    row = session.exec(
        select(
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
    ).one()

    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0

    recent = list(
        session.exec(
            select(AnalysisJob.started_at, AnalysisJob.finished_at)
            .where(col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED)
            .order_by(col(AnalysisJob.finished_at).desc())
            .limit(_SAMPLE_SIZE)
        )
    )
    avg_job_sec = None
    if recent:
        durations = [(f - s).total_seconds() for s, f in recent if s and f and f > s]
        if durations:
            avg_job_sec = sum(durations) / len(durations)

    remaining = queued + running
    pct_done = (completed + failed) / total if total else 0.0
    eta_seconds = None
    eta_at = None
    if avg_job_sec and remaining > 0:
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


@router.get("/stats", response_model=StatsResponse)
def get_stats(session: Session = Depends(get_session)) -> StatsResponse:
    return StatsResponse(
        scrape=_scrape_stats(session),
        analysis=_analysis_stats(session),
        as_of=_utcnow(),
    )
