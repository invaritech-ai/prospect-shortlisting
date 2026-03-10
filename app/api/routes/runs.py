from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast
from sqlmodel import Session, col, select

from app.api.schemas.run import RunCreateRequest, RunCreateResult, RunRead
from app.db.session import get_session
from app.models import Company, Prompt, Run
from app.services.analysis_service import AnalysisService
from app.services.outbox_service import OutboxService


router = APIRouter(prefix="/v1", tags=["runs"])
analysis_service = AnalysisService()
outbox_service = OutboxService()


def _as_run_read(run: Run, prompt_name: str) -> RunRead:
    return RunRead(
        id=run.id,
        upload_id=run.upload_id,
        prompt_id=run.prompt_id,
        prompt_name=prompt_name,
        general_model=run.general_model,
        classify_model=run.classify_model,
        ocr_model=run.ocr_model,
        status=run.status,
        total_jobs=run.total_jobs,
        completed_jobs=run.completed_jobs,
        failed_jobs=run.failed_jobs,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.post("/runs", response_model=RunCreateResult, status_code=status.HTTP_201_CREATED)
def create_runs(payload: RunCreateRequest, session: Session = Depends(get_session)) -> RunCreateResult:
    prompt = session.get(Prompt, payload.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    if payload.scope == "all":
        companies = list(session.exec(select(Company).order_by(col(Company.created_at).asc(), col(Company.domain).asc())))
    else:
        requested_ids = list(dict.fromkeys(payload.company_ids or []))
        companies = list(session.exec(select(Company).where(col(Company.id).in_(requested_ids))))

    if not companies:
        raise HTTPException(status_code=422, detail="No companies available for classification.")

    try:
        runs, jobs, skipped_company_ids = analysis_service.create_runs(
            session=session,
            companies=companies,
            prompt_id=payload.prompt_id,
            general_model=payload.general_model,
            classify_model=payload.classify_model,
            ocr_model=payload.ocr_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Write outbox rows for all jobs in the same transaction as the runs/jobs,
    # then commit everything atomically. analysis_service.create_runs only flushes.
    for job in jobs:
        outbox_service.write(
            session=session,
            job_id=job.id,
            task_type="analysis_job",
            payload={"analysis_job_id": str(job.id)},
        )
    session.commit()

    return RunCreateResult(
        requested_count=len(companies),
        queued_count=len(jobs),
        skipped_company_ids=skipped_company_ids,
        runs=[_as_run_read(run, prompt.name) for run in runs],
    )


@router.get("/runs", response_model=list[RunRead])
def list_runs(
    session: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[RunRead]:
    prompt_name_subquery = (
        select(
            Prompt.id.label("prompt_id"),
            cast(Prompt.name, String()).label("prompt_name"),
        ).subquery()
    )
    rows = list(
        session.exec(
            select(Run, prompt_name_subquery.c.prompt_name)
            .join(prompt_name_subquery, prompt_name_subquery.c.prompt_id == Run.prompt_id)
            .order_by(col(Run.created_at).desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return [_as_run_read(run, prompt_name) for run, prompt_name in rows]


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: UUID, session: Session = Depends(get_session)) -> RunRead:
    row = session.exec(
        select(Run, Prompt.name)
        .join(Prompt, Prompt.id == Run.prompt_id)
        .where(col(Run.id) == run_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found.")
    run, prompt_name = row
    return _as_run_read(run, prompt_name)
