from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import case, update
from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.db.session import get_session
from app.models import AnalysisJob, ScrapeJob
from app.models.pipeline import AnalysisJobState, Run, RunStatus
from app.services.queue_service import QueueService


queue_service = QueueService(consumer_name="worker-stats")


router = APIRouter(prefix="/v1", tags=["stats"])

_SAMPLE_SIZE = 100  # recent completed jobs used to estimate average duration


class PipelineStageStats(BaseModel):
    total: int
    completed: int
    failed: int
    running: int
    queued: int
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
    total = session.exec(select(func.count()).select_from(ScrapeJob)).one() or 0
    completed = session.exec(
        select(func.count()).select_from(ScrapeJob).where(col(ScrapeJob.status) == "completed")
    ).one() or 0
    failed = session.exec(
        select(func.count()).select_from(ScrapeJob).where(
            col(ScrapeJob.terminal_state).is_(True) & (col(ScrapeJob.status) != "completed")
        )
    ).one() or 0
    running = session.exec(
        select(func.count()).select_from(ScrapeJob).where(
            col(ScrapeJob.terminal_state).is_(False)
            & col(ScrapeJob.status).in_(["running_step1", "running_step2", "step1_completed"])
        )
    ).one() or 0
    queued = session.exec(
        select(func.count()).select_from(ScrapeJob).where(col(ScrapeJob.status) == "created")
    ).one() or 0

    # Average full-pipeline duration from recent completions (step1 start → step2 finish).
    recent = list(
        session.exec(
            select(ScrapeJob.step1_started_at, ScrapeJob.step2_finished_at)
            .where(
                col(ScrapeJob.status) == "completed"
            )
            .order_by(col(ScrapeJob.step2_finished_at).desc())
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
        eta_at = datetime.fromtimestamp(_utcnow().timestamp() + eta_seconds, tz=timezone.utc)

    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        running=running,
        queued=queued,
        pct_done=round(pct_done * 100, 1),
        avg_job_sec=round(avg_job_sec, 1) if avg_job_sec else None,
        eta_seconds=round(eta_seconds, 0) if eta_seconds else None,
        eta_at=eta_at,
    )


def _analysis_stats(session: Session) -> PipelineStageStats:
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
        eta_at = datetime.fromtimestamp(_utcnow().timestamp() + eta_seconds, tz=timezone.utc)

    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        running=running,
        queued=queued,
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
    drained: int
    cancelled_db_jobs: int
    queue_key: str


class ResetStuckResult(BaseModel):
    reset_count: int


@router.post("/queue/drain", response_model=DrainQueueResult)
def drain_queue(session: Session = Depends(get_session)) -> DrainQueueResult:
    """Delete all pending tasks from the Redis queue and mark queued DB jobs as cancelled."""
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    queue_key = settings.redis_queue_key

    # Count items before deleting
    drained = redis.llen(queue_key)
    if drained:
        redis.delete(queue_key)

    # Cancel ScrapeJob records still in "created" state
    queued_scrape = list(
        session.exec(select(ScrapeJob).where(col(ScrapeJob.status) == "created"))
    )
    for job in queued_scrape:
        job.status = "cancelled"
        job.terminal_state = True
        session.add(job)

    # Cancel AnalysisJob records still in QUEUED state (stranded when queue was drained)
    queued_analysis = list(
        session.exec(
            select(AnalysisJob).where(
                col(AnalysisJob.terminal_state).is_(False)
                & (col(AnalysisJob.state) == AnalysisJobState.QUEUED)
            )
        )
    )
    for job in queued_analysis:
        job.state = AnalysisJobState.DEAD
        job.terminal_state = True
        session.add(job)

    session.commit()

    return DrainQueueResult(
        drained=int(drained),
        cancelled_db_jobs=len(queued_scrape) + len(queued_analysis),
        queue_key=queue_key,
    )


@router.post("/jobs/reset-stuck", response_model=ResetStuckResult)
def reset_stuck_jobs(session: Session = Depends(get_session)) -> ResetStuckResult:
    """Re-queue scrape jobs that are stuck in a running or incomplete state.

    Jobs in ``step1_completed`` only need their lock cleared — step1 already
    succeeded and ``scrape_run_all`` will skip directly to step2.
    Jobs in ``running_step1`` / ``running_step2`` are reset to ``created``
    so the full pipeline reruns.
    """
    # Jobs where step1 completed but step2 never started (lock not cleared).
    # Just clear the lock; keep status so step2 can claim immediately.
    step1_done_stuck = list(
        session.exec(
            select(ScrapeJob).where(
                col(ScrapeJob.terminal_state).is_(False)
                & (col(ScrapeJob.status) == "step1_completed")
            )
        )
    )
    for job in step1_done_stuck:
        job.lock_token = None
        job.lock_expires_at = None
        session.add(job)

    # Jobs genuinely stuck mid-run — reset to start so step1 reruns cleanly.
    running_stuck = list(
        session.exec(
            select(ScrapeJob).where(
                col(ScrapeJob.terminal_state).is_(False)
                & col(ScrapeJob.status).in_(["running_step1", "running_step2"])
            )
        )
    )
    for job in running_stuck:
        job.status = "created"
        job.terminal_state = False
        job.lock_token = None
        job.lock_expires_at = None
        session.add(job)

    session.commit()

    # Re-enqueue all: scrape_run_all handles both cases correctly.
    # For step1_completed jobs: run_step1 CAS-misses (status wrong), then
    # _run_all checks stage1_status == "completed" and proceeds to step2.
    all_stuck = step1_done_stuck + running_stuck
    for job in all_stuck:
        queue_service.enqueue(task_type="scrape_run_all", payload={"job_id": str(job.id)})

    return ResetStuckResult(reset_count=len(all_stuck))


class MarkFailedResult(BaseModel):
    marked_count: int


@router.post("/jobs/mark-non-completed-failed", response_model=MarkFailedResult)
def mark_non_completed_failed(session: Session = Depends(get_session)) -> MarkFailedResult:
    """Mark all non-completed scrape jobs (cancelled, stuck-running, etc.) as failed/terminal.

    Use this to clean up DB state so the job list accurately reflects what actually ran.
    """
    non_completed = list(
        session.exec(
            select(ScrapeJob).where(
                (col(ScrapeJob.status) != "completed")
                & (col(ScrapeJob.status) != "failed")
            )
        )
    )
    for job in non_completed:
        job.status = "failed"
        job.terminal_state = True
        session.add(job)
    session.commit()
    return MarkFailedResult(marked_count=len(non_completed))


class ResetStuckAnalysisResult(BaseModel):
    reset_count: int


@router.post("/analysis-jobs/reset-stuck", response_model=ResetStuckAnalysisResult)
def reset_stuck_analysis_jobs(session: Session = Depends(get_session)) -> ResetStuckAnalysisResult:
    """Reset analysis jobs stuck in RUNNING or orphaned QUEUED state and re-enqueue them."""
    stuck = list(
        session.exec(
            select(AnalysisJob).where(
                col(AnalysisJob.terminal_state).is_(False)
                & col(AnalysisJob.state).in_([AnalysisJobState.RUNNING, AnalysisJobState.QUEUED])
            )
        )
    )
    for job in stuck:
        job.state = AnalysisJobState.QUEUED
        job.started_at = None
        job.lock_token = None
        job.lock_expires_at = None
        session.add(job)
    session.commit()

    for job in stuck:
        queue_service.enqueue(task_type="analysis_job", payload={"analysis_job_id": str(job.id)})

    return ResetStuckAnalysisResult(reset_count=len(stuck))


class MarkEmptyCompletedResult(BaseModel):
    marked_count: int


@router.post("/jobs/mark-empty-completed-failed", response_model=MarkEmptyCompletedResult)
def mark_empty_completed_failed(session: Session = Depends(get_session)) -> MarkEmptyCompletedResult:
    """Mark scrape jobs that are 'completed' but produced zero markdown pages as failed.

    These are ghost completions — the job ran but extracted nothing classifiable.
    """
    empty = list(
        session.exec(
            select(ScrapeJob).where(
                (col(ScrapeJob.status) == "completed")
                & (col(ScrapeJob.markdown_pages_count) == 0)
            )
        )
    )
    for job in empty:
        job.status = "failed"
        job.terminal_state = True
        if not job.last_error_code:
            job.last_error_code = "no_markdown_produced"
        session.add(job)
    session.commit()
    return MarkEmptyCompletedResult(marked_count=len(empty))


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
    for run in runs:
        if run.total_jobs == 0:
            continue
        run_id = run.id
        succeeded = session.exec(
            select(func.count()).select_from(AnalysisJob).where(
                (col(AnalysisJob.run_id) == run_id)
                & (col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED)
            )
        ).one() or 0
        failed = session.exec(
            select(func.count()).select_from(AnalysisJob).where(
                (col(AnalysisJob.run_id) == run_id)
                & col(AnalysisJob.state).in_([AnalysisJobState.FAILED, AnalysisJobState.DEAD])
            )
        ).one() or 0
        terminal = session.exec(
            select(func.count()).select_from(AnalysisJob).where(
                (col(AnalysisJob.run_id) == run_id)
                & col(AnalysisJob.terminal_state).is_(True)
            )
        ).one() or 0

        run.completed_jobs = succeeded
        run.failed_jobs = failed
        is_done = terminal >= run.total_jobs
        if is_done:
            run.status = RunStatus.FAILED if failed > 0 else RunStatus.COMPLETED
            if not run.finished_at:
                run.finished_at = datetime.now(timezone.utc)
        else:
            run.status = RunStatus.RUNNING
        session.add(run)

    session.commit()
    return RefreshRunStatusResult(refreshed_count=len(runs))
