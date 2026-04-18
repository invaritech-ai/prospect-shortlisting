"""Operator queue-management endpoints: drain, reset stuck, mark failed, refresh runs."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, update
from sqlmodel import Session, col, func, select

from app.db.session import get_session
from app.models import AnalysisJob, Run, ScrapeJob
from app.models.pipeline import AnalysisJobState, RunStatus
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
