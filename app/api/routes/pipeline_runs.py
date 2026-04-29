from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.routes.scrape_actions import _enqueue_scrapes_for_companies
from app.api.schemas.pipeline_run import (
    CostReconciliationSummaryRead,
    PipelineCostSummaryRead,
    PipelineRunProgressRead,
    PipelineRunStartRequest,
    PipelineRunStartResponse,
    PipelineStageCostRead,
    PipelineStageProgressRead,
)
from app.db.session import get_session
from app.core.config import settings
from app.models import (
    AiUsageEvent,
    AnalysisJob,
    Campaign,
    Company,
    ContactFetchJob,
    ContactVerifyJob,
    PipelineRun,
    PipelineRunEvent,
    Prompt,
    ScrapeJob,
    Upload,
)
from app.models.pipeline import (
    PipelineRunStatus,
    PipelineStage,
    utcnow,
)
from app.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyUnavailableError,
    check_idempotency,
    clear_idempotency_reservation,
    normalize_idempotency_key,
    store_idempotency_response,
)
from app.services.run_service import RunService
from app.tasks.analysis import run_analysis_job

router = APIRouter(prefix="/v1", tags=["pipeline-runs"])
run_service = RunService()


def _zero_progress() -> PipelineStageProgressRead:
    return PipelineStageProgressRead(queued=0, running=0, completed=0, failed=0, total=0)


def _increment_progress(counter: PipelineStageProgressRead, status: str) -> None:
    normalized = (status or "").lower()
    if normalized in {"created", "queued"}:
        counter.queued += 1
    elif normalized == "running":
        counter.running += 1
    elif normalized == "succeeded":
        counter.completed += 1
    elif normalized in {"failed", "dead", "cancelled"}:
        counter.failed += 1
    counter.total += 1


def _empty_cost_summary(*, pipeline_run_id: UUID | None = None, campaign_id: UUID | None = None) -> PipelineCostSummaryRead:
    return PipelineCostSummaryRead(
        pipeline_run_id=pipeline_run_id,
        campaign_id=campaign_id,
        total_cost_usd=Decimal("0"),
        event_count=0,
        input_tokens=0,
        output_tokens=0,
        by_stage={},
    )


def _build_cost_summary(*, session: Session, where_clause, pipeline_run_id: UUID | None = None, campaign_id: UUID | None = None) -> PipelineCostSummaryRead:
    totals = session.exec(
        select(
            func.coalesce(func.sum(AiUsageEvent.billed_cost_usd), 0),
            func.count(AiUsageEvent.id),
            func.coalesce(func.sum(AiUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(AiUsageEvent.output_tokens), 0),
        ).where(where_clause)
    ).one()
    if totals is None:
        return _empty_cost_summary(pipeline_run_id=pipeline_run_id, campaign_id=campaign_id)

    by_stage_rows = list(
        session.exec(
            select(
                AiUsageEvent.stage,
                func.coalesce(func.sum(AiUsageEvent.billed_cost_usd), 0),
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.input_tokens), 0),
                func.coalesce(func.sum(AiUsageEvent.output_tokens), 0),
            )
            .where(where_clause)
            .group_by(AiUsageEvent.stage)
        )
    )
    by_stage: dict[str, PipelineStageCostRead] = {}
    for stage, cost, event_count, input_tokens, output_tokens in by_stage_rows:
        by_stage[str(stage)] = PipelineStageCostRead(
            cost_usd=Decimal(str(cost or 0)),
            event_count=int(event_count or 0),
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
        )

    total_cost, total_events, total_input_tokens, total_output_tokens = totals
    return PipelineCostSummaryRead(
        pipeline_run_id=pipeline_run_id,
        campaign_id=campaign_id,
        total_cost_usd=Decimal(str(total_cost or 0)),
        event_count=int(total_events or 0),
        input_tokens=int(total_input_tokens or 0),
        output_tokens=int(total_output_tokens or 0),
        by_stage=by_stage,
    )


@router.post("/pipeline-runs/start", response_model=PipelineRunStartResponse)
def start_pipeline_run(
    payload: PipelineRunStartRequest,
    session: Session = Depends(get_session),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> PipelineRunStartResponse:
    try:
        idempotency_key = normalize_idempotency_key(x_idempotency_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    request_payload = payload.model_dump(mode="json", exclude_none=True)
    request_payload["route"] = "pipeline-runs/start"
    try:
        replay = check_idempotency(
            namespace="pipeline-runs-start",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
    except IdempotencyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if replay.replayed and replay.response is not None:
        return PipelineRunStartResponse(**replay.response)

    run: PipelineRun | None = None
    try:
        campaign = session.get(Campaign, payload.campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found.")

        analysis_prompt_id: UUID | None = None
        raw_prompt_id = (payload.analysis_prompt_snapshot or {}).get("prompt_id") or (
            payload.analysis_prompt_snapshot or {}
        ).get("selected_prompt_id")
        if raw_prompt_id is not None:
            try:
                analysis_prompt_id = UUID(str(raw_prompt_id))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Invalid analysis prompt id in snapshot.") from exc
        if analysis_prompt_id is None:
            raise HTTPException(
                status_code=422,
                detail="analysis_prompt_snapshot.prompt_id is required for chained S2 execution.",
            )
        prompt = session.get(Prompt, analysis_prompt_id)
        if prompt is None or not prompt.enabled:
            raise HTTPException(
                status_code=422,
                detail="Selected analysis prompt is missing or disabled.",
            )

        if payload.company_ids:
            requested_company_ids = list(dict.fromkeys(payload.company_ids))
            resolved_company_ids: list[UUID] = []
            for raw_id in requested_company_ids:
                try:
                    resolved_company_ids.append(UUID(str(raw_id)))
                except ValueError:
                    continue
            companies = (
                list(
                    session.exec(
                        select(Company)
                        .join(Upload, col(Upload.id) == col(Company.upload_id))
                        .where(
                            col(Company.id).in_(resolved_company_ids),
                            col(Upload.campaign_id) == payload.campaign_id,
                        )
                    )
                )
                if resolved_company_ids
                else []
            )
        else:
            resolved_company_ids = list(
                session.exec(
                    select(Company.id)
                    .join(Upload, col(Upload.id) == col(Company.upload_id))
                    .where(col(Upload.campaign_id) == payload.campaign_id)
                )
            )
            requested_company_ids = [str(company_id) for company_id in resolved_company_ids]
            companies = (
                list(session.exec(select(Company).where(col(Company.id).in_(resolved_company_ids))))
                if resolved_company_ids
                else []
            )

        run = PipelineRun(
            campaign_id=payload.campaign_id,
            state=PipelineRunStatus.RUNNING,
            company_ids_snapshot=[str(company_id) for company_id in resolved_company_ids],
            scrape_rules_snapshot=payload.scrape_rules_snapshot,
            analysis_prompt_snapshot=payload.analysis_prompt_snapshot,
            contact_rules_snapshot=payload.contact_rules_snapshot,
            validation_policy_snapshot=payload.validation_policy_snapshot,
            requested_count=len(requested_company_ids),
            skipped_count=max(0, len(requested_company_ids) - len(companies)),
            created_at=utcnow(),
            updated_at=utcnow(),
            started_at=utcnow(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        force_s1 = bool((payload.force_rerun or {}).get("scrape"))
        companies_for_s1 = companies
        reused_company_ids: list[UUID] = []
        if companies and not force_s1:
            normalized_urls = [c.normalized_url for c in companies if c.normalized_url]
            latest_completed_by_url: dict[str, ScrapeJob] = {}
            if normalized_urls:
                rows = list(
                    session.exec(
                        select(ScrapeJob)
                        .where(
                            col(ScrapeJob.normalized_url).in_(normalized_urls),
                            col(ScrapeJob.state) == "succeeded",
                            col(ScrapeJob.terminal_state).is_(True),
                        )
                        .order_by(col(ScrapeJob.created_at).desc())
                    )
                )
                for scrape_job in rows:
                    if scrape_job.normalized_url not in latest_completed_by_url:
                        latest_completed_by_url[scrape_job.normalized_url] = scrape_job
            companies_for_s1 = []
            for company in companies:
                if latest_completed_by_url.get(company.normalized_url):
                    reused_company_ids.append(company.id)
                    continue
                companies_for_s1.append(company)

        enqueue_result = _enqueue_scrapes_for_companies(
            session=session,
            companies=companies_for_s1,
            scrape_rules=payload.scrape_rules_snapshot,
            idempotency_key=None,
            pipeline_run_id=run.id,
        )

        failed_count = len(enqueue_result.failed_company_ids)
        queued_count = enqueue_result.queued_count
        reused_count = len(reused_company_ids)
        s2_jobs_count = 0
        if reused_company_ids:
            reused_companies = list(
                session.exec(select(Company).where(col(Company.id).in_(reused_company_ids)))
            )
            _runs, jobs, _ = run_service.create_runs(
                session=session,
                companies=reused_companies,
                prompt_id=analysis_prompt_id,
                general_model=settings.general_model,
                classify_model=settings.classify_model,
                pipeline_run_id=run.id,
            )
            # Runs/jobs are flushed by service; queue jobs now, commit below.
            for job in jobs:
                run_analysis_job.delay(str(job.id))
            s2_jobs_count = len(jobs)
        run.reused_count = reused_count
        run.queued_count = queued_count
        run.failed_count = failed_count
        run.updated_at = utcnow()
        session.add(run)
        session.add(
            PipelineRunEvent(
                pipeline_run_id=run.id,
                stage=PipelineStage.SCRAPE.value,
                event_type="start_requested",
                payload_json={
                    "requested_count": run.requested_count,
                    "queued_count": queued_count,
                    "reused_count": reused_count,
                    "reused_company_ids_count": reused_count,
                    "skipped_count": run.skipped_count,
                    "failed_count": failed_count,
                },
            )
        )
        if reused_company_ids:
            session.add(
                PipelineRunEvent(
                    pipeline_run_id=run.id,
                    stage=PipelineStage.ANALYSIS.value,
                    event_type="reused_s1_queued_s2",
                    payload_json={
                        "reused_company_ids_count": len(reused_company_ids),
                        "queued_analysis_jobs_count": s2_jobs_count,
                    },
                )
            )
        session.commit()

        response = PipelineRunStartResponse(
            pipeline_run_id=run.id,
            requested_count=run.requested_count,
            reused_count=run.reused_count,
            queued_count=run.queued_count,
            skipped_count=run.skipped_count,
            failed_count=run.failed_count,
        )
        store_idempotency_response(
            namespace="pipeline-runs-start",
            idempotency_key=idempotency_key,
            payload=request_payload,
            response=response.model_dump(mode="json"),
        )
        return response
    except Exception:
        if run is not None:
            run.state = PipelineRunStatus.FAILED
            run.finished_at = utcnow()
            run.updated_at = utcnow()
            session.add(run)
            session.commit()
        clear_idempotency_reservation(
            namespace="pipeline-runs-start",
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
        raise


@router.get("/pipeline-runs/{run_id}/progress", response_model=PipelineRunProgressRead)
def get_pipeline_run_progress(run_id: UUID, session: Session = Depends(get_session)) -> PipelineRunProgressRead:
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")

    stages: dict[str, PipelineStageProgressRead] = {
        PipelineStage.SCRAPE.value: _zero_progress(),
        PipelineStage.ANALYSIS.value: _zero_progress(),
        PipelineStage.CONTACTS.value: _zero_progress(),
        PipelineStage.VALIDATION.value: _zero_progress(),
    }

    for status in session.exec(select(ScrapeJob.state).where(col(ScrapeJob.pipeline_run_id) == run_id)).all():
        _increment_progress(stages[PipelineStage.SCRAPE.value], str(status))
    for state in session.exec(select(AnalysisJob.state).where(col(AnalysisJob.pipeline_run_id) == run_id)).all():
        _increment_progress(stages[PipelineStage.ANALYSIS.value], str(state))
    for state in session.exec(select(ContactFetchJob.state).where(col(ContactFetchJob.pipeline_run_id) == run_id)).all():
        _increment_progress(stages[PipelineStage.CONTACTS.value], str(state))
    for state in session.exec(select(ContactVerifyJob.state).where(col(ContactVerifyJob.pipeline_run_id) == run_id)).all():
        _increment_progress(stages[PipelineStage.VALIDATION.value], str(state))

    total_stage_rows = sum(stage.total for stage in stages.values())
    terminal_stage_rows = sum(stage.completed + stage.failed for stage in stages.values())
    computed_status = run.state
    if total_stage_rows > 0 and terminal_stage_rows >= total_stage_rows:
        computed_status = PipelineRunStatus.SUCCEEDED if run.failed_count == 0 else PipelineRunStatus.FAILED

    return PipelineRunProgressRead(
        pipeline_run_id=run.id,
        campaign_id=run.campaign_id,
        state=computed_status,
        requested_count=run.requested_count,
        reused_count=run.reused_count,
        queued_count=run.queued_count,
        skipped_count=run.skipped_count,
        failed_count=run.failed_count,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stages=stages,
    )


@router.get("/pipeline-runs/{run_id}/costs", response_model=PipelineCostSummaryRead)
def get_pipeline_run_costs(run_id: UUID, session: Session = Depends(get_session)) -> PipelineCostSummaryRead:
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")
    return _build_cost_summary(
        session=session,
        where_clause=(col(AiUsageEvent.pipeline_run_id) == run_id),
        pipeline_run_id=run_id,
        campaign_id=run.campaign_id,
    )


@router.get("/campaigns/{campaign_id}/costs", response_model=PipelineCostSummaryRead)
def get_campaign_costs(campaign_id: UUID, session: Session = Depends(get_session)) -> PipelineCostSummaryRead:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return _build_cost_summary(
        session=session,
        where_clause=(col(AiUsageEvent.campaign_id) == campaign_id),
        campaign_id=campaign_id,
    )


@router.get("/costs/reconciliation-summary", response_model=CostReconciliationSummaryRead)
def get_cost_reconciliation_summary(session: Session = Depends(get_session)) -> CostReconciliationSummaryRead:
    rows = list(
        session.exec(
            select(
                AiUsageEvent.reconciliation_status,
                func.count(AiUsageEvent.id),
            ).group_by(AiUsageEvent.reconciliation_status)
        )
    )
    by_status: dict[str, int] = {}
    total_events = 0
    for status, count in rows:
        key = str(status or "unknown")
        value = int(count or 0)
        by_status[key] = value
        total_events += value
    return CostReconciliationSummaryRead(total_events=total_events, by_status=by_status)
