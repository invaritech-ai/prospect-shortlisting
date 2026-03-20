from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, update
from sqlmodel import Session, col, func, select

from app.db.session import get_session
from app.models import AnalysisJob, ScrapeJob
from app.models.pipeline import AnalysisJobState, Run, RunStatus


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
    total = session.exec(select(func.count()).select_from(ScrapeJob)).one() or 0
    completed = session.exec(
        select(func.count()).select_from(ScrapeJob).where(col(ScrapeJob.status) == "completed")
    ).one() or 0
    site_unavailable = session.exec(
        select(func.count()).select_from(ScrapeJob).where(
            col(ScrapeJob.status) == "site_unavailable"
        )
    ).one() or 0
    failed = session.exec(
        select(func.count()).select_from(ScrapeJob).where(
            col(ScrapeJob.terminal_state).is_(True)
            & (col(ScrapeJob.status) != "completed")
            & (col(ScrapeJob.status) != "site_unavailable")
        )
    ).one() or 0
    running = session.exec(
        select(func.count()).select_from(ScrapeJob).where(
            col(ScrapeJob.terminal_state).is_(False)
            & (col(ScrapeJob.status) == "running")
        )
    ).one() or 0
    queued = session.exec(
        select(func.count()).select_from(ScrapeJob).where(col(ScrapeJob.status) == "created")
    ).one() or 0

    # Stuck = running but not updated within the expected window.
    stuck_cutoff = now - timedelta(minutes=SCRAPE_RUNNING_STUCK_MINUTES)
    stuck_count = session.exec(
        select(func.count()).select_from(ScrapeJob).where(
            col(ScrapeJob.terminal_state).is_(False)
            & (col(ScrapeJob.status) == "running")
            & (col(ScrapeJob.updated_at) < stuck_cutoff)
        )
    ).one() or 0

    # Average full-pipeline duration from recent completions.
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
        durations = [
            (f - s).total_seconds()
            for s, f in recent
            if s and f and f > s
        ]
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
    total = session.exec(select(func.count()).select_from(AnalysisJob)).one() or 0
    completed = session.exec(
        select(func.count()).select_from(AnalysisJob).where(
            col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED
        )
    ).one() or 0
    failed = session.exec(
        select(func.count()).select_from(AnalysisJob).where(
            col(AnalysisJob.state).in_([AnalysisJobState.FAILED, AnalysisJobState.DEAD])
        )
    ).one() or 0
    running = session.exec(
        select(func.count()).select_from(AnalysisJob).where(
            col(AnalysisJob.state) == AnalysisJobState.RUNNING
        )
    ).one() or 0
    queued = session.exec(
        select(func.count()).select_from(AnalysisJob).where(
            col(AnalysisJob.state) == AnalysisJobState.QUEUED
        )
    ).one() or 0

    # Stuck = RUNNING with expired lock.
    stuck_count = session.exec(
        select(func.count()).select_from(AnalysisJob).where(
            col(AnalysisJob.terminal_state).is_(False)
            & (col(AnalysisJob.state) == AnalysisJobState.RUNNING)
            & col(AnalysisJob.lock_expires_at).is_not(None)
            & (col(AnalysisJob.lock_expires_at) < now)
        )
    ).one() or 0

    recent = list(
        session.exec(
            select(AnalysisJob.started_at, AnalysisJob.finished_at)
            .where(col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED)
            .order_by(col(AnalysisJob.finished_at).desc())
            .limit(_SAMPLE_SIZE)
        )
    )
    avg_job_sec: float | None = None
    if recent:
        durations = [
            (f - s).total_seconds()
            for s, f in recent
            if s and f and f > s
        ]
        if durations:
            avg_job_sec = sum(durations) / len(durations)

    remaining = queued + running
    pct_done = (completed + failed) / total if total else 0.0
    eta_seconds: float | None = None
    eta_at: datetime | None = None
    if avg_job_sec and remaining > 0:
        eta_seconds = remaining * avg_job_sec
        eta_at = datetime.fromtimestamp(now.timestamp() + eta_seconds, tz=timezone.utc)

    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        site_unavailable=0,  # not applicable to analysis jobs
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


# ---------------------------------------------------------------------------
# Queue management
# ---------------------------------------------------------------------------


class DrainQueueResult(BaseModel):
    cancelled_scrape_jobs: int
    cancelled_analysis_jobs: int


class ResetStuckResult(BaseModel):
    reset_count: int


@router.post("/queue/drain", response_model=DrainQueueResult)
def drain_queue(session: Session = Depends(get_session)) -> DrainQueueResult:
    """Cancel all queued work. Workers will no-op any in-flight tasks because
    the DB state will no longer be claimable."""
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
            .values(status="created", lock_token=None, lock_expires_at=None)
        )
        session.commit()
        for job_id in stuck_ids:
            scrape_website.delay(str(job_id))

    return ResetStuckResult(reset_count=len(stuck_ids))


class MarkFailedResult(BaseModel):
    marked_count: int


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


class ResetStuckAnalysisResult(BaseModel):
    reset_count: int


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
            )
        )
        session.commit()
        for job_id in stuck_ids:
            run_analysis_job.delay(str(job_id))

    return ResetStuckAnalysisResult(reset_count=len(stuck_ids))


class MarkEmptyCompletedResult(BaseModel):
    marked_count: int


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
            # Only set error_code if not already set (COALESCE preserves existing value)
            last_error_code=func.coalesce(ScrapeJob.last_error_code, "no_markdown_produced"),
        )
    )
    session.commit()
    return MarkEmptyCompletedResult(marked_count=result.rowcount or 0)  # type: ignore[union-attr]


class RefreshRunStatusResult(BaseModel):
    refreshed_count: int


@router.post("/runs/refresh-status", response_model=RefreshRunStatusResult)
def refresh_run_statuses(session: Session = Depends(get_session)) -> RefreshRunStatusResult:
    """Recalculate status/progress for all non-completed runs based on current job states."""
    runs = list(
        session.exec(
            select(Run).where(
                col(Run.status).in_([RunStatus.RUNNING, RunStatus.CREATED])
            )
        )
    )
    if not runs:
        return RefreshRunStatusResult(refreshed_count=0)

    run_ids = [r.id for r in runs]

    # Single query: counts per run_id using conditional aggregation.
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

    counts: dict = {row.run_id: row for row in agg_rows}

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
