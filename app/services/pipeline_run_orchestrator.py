from __future__ import annotations

from uuid import UUID

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import (
    AnalysisJob,
    ClassificationResult,
    Company,
    ContactFetchJob,
    PipelineRun,
    PipelineRunEvent,
    Prompt,
    ScrapeJob,
)
from app.models.pipeline import (
    AnalysisJobState,
    CompanyPipelineStage,
    PipelineStage,
    PredictedLabel,
)
from app.services.contact_queue_service import ContactQueueService
from app.services.contact_runtime_service import ContactRuntimeService
from app.services.run_service import RunService


def _parse_prompt_id(snapshot: dict | None) -> UUID | None:
    if not snapshot:
        return None
    raw = snapshot.get("prompt_id") or snapshot.get("selected_prompt_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _snapshot_company_ids(run: PipelineRun) -> set[UUID]:
    ids: set[UUID] = set()
    for raw in run.company_ids_snapshot or []:
        try:
            ids.add(UUID(str(raw)))
        except (TypeError, ValueError):
            continue
    return ids


def enqueue_s2_for_scrape_success(engine: Engine, scrape_job_id: UUID) -> None:
    with Session(engine) as session:
        scrape_job = session.get(ScrapeJob, scrape_job_id)
        if (
            scrape_job is None
            or scrape_job.pipeline_run_id is None
            or not scrape_job.terminal_state
            or scrape_job.state != "succeeded"
        ):
            return
        run = session.get(PipelineRun, scrape_job.pipeline_run_id)
        if run is None:
            return

        prompt_id = _parse_prompt_id(run.analysis_prompt_snapshot)
        if prompt_id is None or session.get(Prompt, prompt_id) is None:
            return

        company_ids = _snapshot_company_ids(run)
        if not company_ids:
            return
        companies = list(
            session.exec(
                select(Company).where(
                    col(Company.normalized_url) == scrape_job.normalized_url,
                    col(Company.id).in_(company_ids),
                )
            )
        )
        if not companies:
            return

        queued_runs, queued_jobs, skipped_company_ids = RunService().create_runs(
            session=session,
            companies=companies,
            prompt_id=prompt_id,
            general_model=settings.general_model,
            classify_model=settings.classify_model,
            pipeline_run_id=run.id,
        )
        if not queued_jobs:
            return

        session.add(
            PipelineRunEvent(
                pipeline_run_id=run.id,
                stage=PipelineStage.ANALYSIS.value,
                event_type="s1_to_s2_queued",
                payload_json={
                    "scrape_job_id": str(scrape_job.id),
                    "queued_analysis_jobs": len(queued_jobs),
                    "queued_runs": len(queued_runs),
                    "skipped_companies": len(skipped_company_ids),
                },
            )
        )
        session.commit()

        from app.tasks.analysis import run_analysis_job

        for job in queued_jobs:
            run_analysis_job.delay(str(job.id))


def enqueue_s3_for_analysis_success(engine: Engine, analysis_job_id: UUID) -> None:
    with Session(engine) as session:
        analysis_job = session.get(AnalysisJob, analysis_job_id)
        if (
            analysis_job is None
            or analysis_job.pipeline_run_id is None
            or not analysis_job.terminal_state
            or analysis_job.state != AnalysisJobState.SUCCEEDED
        ):
            return
        runtime = ContactRuntimeService()
        control = runtime.get_or_create_control(session)
        if not control.auto_enqueue_enabled or control.auto_enqueue_paused:
            return
        pipeline_run = session.get(PipelineRun, analysis_job.pipeline_run_id)
        if pipeline_run is None:
            return

        active_company_ids = {
            company_id
            for company_id in session.exec(
                select(ContactFetchJob.company_id).where(
                    col(ContactFetchJob.pipeline_run_id) == pipeline_run.id,
                    col(ContactFetchJob.terminal_state).is_(False),
                )
            )
            if company_id is not None
        }
        eligible_companies = list(
            session.exec(
                select(Company)
                .join(AnalysisJob, col(AnalysisJob.company_id) == col(Company.id))
                .join(ClassificationResult, col(ClassificationResult.analysis_job_id) == col(AnalysisJob.id))
                .where(
                    col(AnalysisJob.pipeline_run_id) == pipeline_run.id,
                    col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED,
                    col(ClassificationResult.predicted_label) == PredictedLabel.POSSIBLE,
                    col(Company.pipeline_stage) == CompanyPipelineStage.CONTACT_READY,
                )
                .order_by(col(Company.domain).asc())
            )
        )
        companies_to_queue = [
            company
            for company in eligible_companies
            if company.id not in active_company_ids
        ][: max(1, control.auto_enqueue_max_batch_size)]
        if not companies_to_queue:
            return

        result = ContactQueueService().enqueue_fetches(
            session=session,
            companies=companies_to_queue,
            provider_mode="both",
            campaign_id=pipeline_run.campaign_id,
            pipeline_run_id=pipeline_run.id,
            trigger_source="pipeline",
            auto_enqueued=True,
        )
        if result.queued_count == 0:
            return
        session.add(
            PipelineRunEvent(
                pipeline_run_id=pipeline_run.id,
                stage=PipelineStage.CONTACTS.value,
                event_type="s2_to_s3_queued",
                payload_json={
                    "analysis_job_id": str(analysis_job.id),
                    "contact_fetch_batch_id": str(result.batch_id) if result.batch_id else None,
                    "contact_fetch_job_ids": [str(job_id) for job_id in result.queued_job_ids],
                    "provider_mode": "both",
                    "queued_count": result.queued_count,
                },
            )
        )
        session.commit()
