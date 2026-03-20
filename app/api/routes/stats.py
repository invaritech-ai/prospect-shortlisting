"""Read-only pipeline stats: counts, averages, ETA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case
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
    now = _utcnow()
    stuck_cutoff = now - timedelta(minutes=SCRAPE_RUNNING_STUCK_MINUTES)

    row = session.exec(
        select(
            func.count().label("total"),
            func.count(case((col(ScrapeJob.status) == "completed", 1))).label("completed"),
            func.count(case((col(ScrapeJob.status) == "site_unavailable", 1))).label("site_unavailable"),
            func.count(case((
                col(ScrapeJob.terminal_state).is_(True)
                & (col(ScrapeJob.status) != "completed")
                & (col(ScrapeJob.status) != "site_unavailable"),
                1,
            ))).label("failed"),
            func.count(case((
                col(ScrapeJob.terminal_state).is_(False) & (col(ScrapeJob.status) == "running"),
                1,
            ))).label("running"),
            func.count(case((col(ScrapeJob.status) == "created", 1))).label("queued"),
            func.count(case((
                col(ScrapeJob.terminal_state).is_(False)
                & (col(ScrapeJob.status) == "running")
                & (col(ScrapeJob.updated_at) < stuck_cutoff),
                1,
            ))).label("stuck_count"),
        ).select_from(ScrapeJob)
    ).one()

    total = row.total or 0
    completed = row.completed or 0
    site_unavailable = row.site_unavailable or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0

    recent = list(
        session.exec(
            select(ScrapeJob.started_at, ScrapeJob.finished_at)
            .where(col(ScrapeJob.status) == "completed")
            .order_by(col(ScrapeJob.finished_at).desc())
            .limit(_SAMPLE_SIZE)
        )
    )
    avg_job_sec: float | None = None
    if recent:
        durations = [(f - s).total_seconds() for s, f in recent if s and f and f > s]
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
