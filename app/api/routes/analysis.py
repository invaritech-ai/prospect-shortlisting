from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast
from sqlmodel import Session, col, select

from app.api.schemas.analysis import AnalysisJobDetailRead, AnalysisPipelineJobRead
from app.db.session import get_session
from app.models import AnalysisJob, ClassificationResult, Company, PipelineRun, Prompt


router = APIRouter(prefix="/v1", tags=["analysis"])


@router.get("/pipeline-runs/{pipeline_run_id}/analysis-jobs", response_model=list[AnalysisPipelineJobRead])
def list_pipeline_run_analysis_jobs(
    pipeline_run_id: UUID,
    session: Session = Depends(get_session),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> list[AnalysisPipelineJobRead]:
    pipeline_run = session.get(PipelineRun, pipeline_run_id)
    if not pipeline_run:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")

    rows = list(
        session.exec(
            select(
                AnalysisJob.id,
                AnalysisJob.pipeline_run_id,
                AnalysisJob.company_id,
                Company.domain,
                cast(AnalysisJob.state, String()),
                AnalysisJob.terminal_state,
                AnalysisJob.last_error_code,
                AnalysisJob.last_error_message,
                cast(ClassificationResult.predicted_label, String()),
                ClassificationResult.confidence,
                AnalysisJob.created_at,
                AnalysisJob.started_at,
                AnalysisJob.finished_at,
            )
            .join(Company, Company.id == AnalysisJob.company_id)
            .outerjoin(ClassificationResult, ClassificationResult.analysis_job_id == AnalysisJob.id)
            .where(col(AnalysisJob.pipeline_run_id) == pipeline_run_id)
            .order_by(col(Company.domain).asc(), col(AnalysisJob.created_at).asc())
            .offset(offset)
            .limit(limit)
        )
    )
    return [
        AnalysisPipelineJobRead(
            analysis_job_id=row[0],
            pipeline_run_id=row[1],
            company_id=row[2],
            domain=row[3],
            state=row[4],
            terminal_state=row[5],
            last_error_code=row[6],
            last_error_message=row[7],
            predicted_label=row[8],
            confidence=float(row[9]) if row[9] is not None else None,
            created_at=row[10],
            started_at=row[11],
            finished_at=row[12],
        )
        for row in rows
    ]


@router.get("/analysis-jobs/{analysis_job_id}", response_model=AnalysisJobDetailRead)
def get_analysis_job_detail(
    analysis_job_id: UUID,
    session: Session = Depends(get_session),
) -> AnalysisJobDetailRead:
    row = session.exec(
        select(
            AnalysisJob.id,
            AnalysisJob.pipeline_run_id,
            AnalysisJob.company_id,
            Company.domain,
            cast(AnalysisJob.state, String()),
            AnalysisJob.terminal_state,
            AnalysisJob.last_error_code,
            AnalysisJob.last_error_message,
            AnalysisJob.created_at,
            AnalysisJob.started_at,
            AnalysisJob.finished_at,
            Prompt.name,
            cast(PipelineRun.state, String()),
            cast(ClassificationResult.predicted_label, String()),
            ClassificationResult.confidence,
            ClassificationResult.reasoning_json,
            ClassificationResult.evidence_json,
        )
        .join(Company, Company.id == AnalysisJob.company_id)
        .outerjoin(PipelineRun, PipelineRun.id == AnalysisJob.pipeline_run_id)
        .join(Prompt, Prompt.id == AnalysisJob.prompt_id)
        .outerjoin(ClassificationResult, ClassificationResult.analysis_job_id == AnalysisJob.id)
        .where(col(AnalysisJob.id) == analysis_job_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Analysis job not found.")

    return AnalysisJobDetailRead(
        analysis_job_id=row[0],
        pipeline_run_id=row[1],
        company_id=row[2],
        domain=row[3],
        state=row[4],
        terminal_state=row[5],
        last_error_code=row[6],
        last_error_message=row[7],
        created_at=row[8],
        started_at=row[9],
        finished_at=row[10],
        prompt_name=row[11],
        pipeline_run_state=row[12],
        predicted_label=row[13],
        confidence=float(row[14]) if row[14] is not None else None,
        reasoning_json=row[15],
        evidence_json=row[16],
    )
