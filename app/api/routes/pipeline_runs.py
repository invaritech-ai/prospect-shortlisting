from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, cast, func
from sqlmodel import Session, col, select

from app.api.schemas.pipeline_run import (
    PipelineRunProgressRead,
    PipelineRunStartRequest,
    PipelineRunStartResponse,
    PipelineStageProgressRead,
)
from app.core.config import settings
from app.db.session import get_session
from app.jobs.ai_decision import run_ai_decision
from app.models import AnalysisJob, Company, PipelineRun, Prompt, Upload
from app.models.pipeline import AnalysisJobState, PipelineRunStatus, utcnow
from app.services.context_service import bulk_ensure_crawl_adapters
from app.services.pipeline_service import latest_usable_scrape

router = APIRouter(prefix="/v1", tags=["pipeline-runs"])


def _analysis_prompt_id(payload: PipelineRunStartRequest) -> UUID:
    snapshot = payload.analysis_prompt_snapshot or {}
    raw = snapshot.get("prompt_id")
    if not raw:
        raise HTTPException(status_code=400, detail="analysis_prompt_snapshot.prompt_id is required.")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid prompt_id.") from exc


def _refresh_run_counts(session: Session, run: PipelineRun) -> None:
    rows = list(
        session.exec(
            select(cast(AnalysisJob.state, String()), func.count(AnalysisJob.id))
            .where(col(AnalysisJob.pipeline_run_id) == run.id)
            .group_by(cast(AnalysisJob.state, String()))
        )
    )
    counts = {state: int(count) for state, count in rows}
    queued = counts.get("queued", 0)
    running = counts.get("running", 0)
    succeeded = counts.get("succeeded", 0)
    failed = counts.get("failed", 0) + counts.get("dead", 0)
    total = queued + running + succeeded + failed

    run.queued_count = queued
    run.failed_count = failed
    if total == 0:
        run.state = PipelineRunStatus.QUEUED
    elif queued > 0 or running > 0:
        run.state = PipelineRunStatus.RUNNING
        run.started_at = run.started_at or utcnow()
        run.finished_at = None
    elif failed > 0:
        run.state = PipelineRunStatus.FAILED
        run.finished_at = utcnow()
    else:
        run.state = PipelineRunStatus.SUCCEEDED
        run.finished_at = utcnow()
    run.updated_at = utcnow()
    session.add(run)


@router.post("/pipeline-runs/start", response_model=PipelineRunStartResponse)
async def start_pipeline_run(
    payload: PipelineRunStartRequest,
    session: Session = Depends(get_session),
) -> PipelineRunStartResponse:
    if not payload.company_ids:
        raise HTTPException(status_code=400, detail="company_ids is required for manual S2.")

    prompt = session.get(Prompt, _analysis_prompt_id(payload))
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    if not prompt.enabled:
        raise HTTPException(status_code=400, detail="Prompt must be enabled for manual S2.")

    company_ids = [UUID(str(company_id)) for company_id in payload.company_ids]
    companies = list(
        session.exec(
            select(Company)
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == payload.campaign_id,
                col(Company.id).in_(company_ids),
            )
        )
    )
    if {company.id for company in companies} != set(company_ids):
        raise HTTPException(status_code=400, detail="One or more company_ids are outside campaign scope.")

    eligible: list[Company] = []
    scrape_map = {}
    for company in companies:
        usable_scrape = latest_usable_scrape(session, company.normalized_url)
        if usable_scrape is None:
            continue
        eligible.append(company)
        scrape_map[company.normalized_url] = usable_scrape

    run = PipelineRun(
        campaign_id=payload.campaign_id,
        state=PipelineRunStatus.QUEUED,
        company_ids_snapshot=[str(company_id) for company_id in company_ids],
        analysis_prompt_snapshot={"prompt_id": str(prompt.id), "prompt_text": prompt.prompt_text},
        requested_count=len(company_ids),
        reused_count=0,
        queued_count=0,
        skipped_count=0,
        failed_count=0,
    )
    session.add(run)
    session.flush()

    artifact_map = bulk_ensure_crawl_adapters(
        session=session,
        companies=eligible,
        scrape_map=scrape_map,
    )

    prompt_hash = hashlib.sha256(prompt.prompt_text.encode()).hexdigest()[:32]
    jobs: list[AnalysisJob] = []
    for company in eligible:
        artifact = artifact_map.get(company.id)
        if artifact is None:
            continue
        jobs.append(
            AnalysisJob(
                pipeline_run_id=run.id,
                upload_id=company.upload_id,
                company_id=company.id,
                crawl_artifact_id=artifact.id,
                prompt_id=prompt.id,
                general_model=settings.general_model,
                classify_model=settings.classify_model,
                state=AnalysisJobState.QUEUED,
                terminal_state=False,
                prompt_hash=prompt_hash,
            )
        )

    session.add_all(jobs)
    run.queued_count = len(jobs)
    run.skipped_count = len(company_ids) - len(jobs)
    run.started_at = utcnow() if jobs else None
    run.updated_at = utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)

    defer_failed = 0
    for job in jobs:
        try:
            await run_ai_decision.defer_async(analysis_job_id=str(job.id))
        except Exception:
            defer_failed += 1

    if defer_failed:
        run.failed_count += defer_failed
        run.queued_count = max(0, run.queued_count - defer_failed)
        run.updated_at = utcnow()
        session.add(run)
        session.commit()
        session.refresh(run)

    return PipelineRunStartResponse(
        pipeline_run_id=run.id,
        requested_count=run.requested_count,
        reused_count=run.reused_count,
        queued_count=run.queued_count,
        skipped_count=run.skipped_count,
        failed_count=run.failed_count,
    )


@router.get("/pipeline-runs/{pipeline_run_id}/progress", response_model=PipelineRunProgressRead)
def get_pipeline_run_progress(
    pipeline_run_id: UUID,
    session: Session = Depends(get_session),
) -> PipelineRunProgressRead:
    run = session.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")

    _refresh_run_counts(session, run)
    session.commit()
    session.refresh(run)

    rows = list(
        session.exec(
            select(cast(AnalysisJob.state, String()), func.count(AnalysisJob.id))
            .where(col(AnalysisJob.pipeline_run_id) == pipeline_run_id)
            .group_by(cast(AnalysisJob.state, String()))
        )
    )
    counts = {state: int(count) for state, count in rows}
    analysis = PipelineStageProgressRead(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        succeeded=counts.get("succeeded", 0),
        failed=counts.get("failed", 0) + counts.get("dead", 0),
        total=sum(counts.values()),
    )

    return PipelineRunProgressRead(
        pipeline_run_id=run.id,
        campaign_id=run.campaign_id,
        state=run.state,
        requested_count=run.requested_count,
        reused_count=run.reused_count,
        queued_count=run.queued_count,
        skipped_count=run.skipped_count,
        failed_count=run.failed_count,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stages={"analysis": analysis},
    )
