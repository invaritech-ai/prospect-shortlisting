from __future__ import annotations

from uuid import UUID

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import (
    AnalysisJob,
    Company,
    ContactFetchJob,
    ContactVerifyJob,
    PipelineRun,
    PipelineRunEvent,
    Prompt,
    ProspectContact,
    ScrapeJob,
)
from app.models.pipeline import AnalysisJobState, ContactFetchJobState, ContactVerifyJobState, PipelineStage
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
            or scrape_job.status != "completed"
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
                stage=PipelineStage.S2_ANALYSIS.value,
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
        existing_active = session.exec(
            select(ContactFetchJob).where(
                col(ContactFetchJob.company_id) == analysis_job.company_id,
                col(ContactFetchJob.pipeline_run_id) == analysis_job.pipeline_run_id,
                col(ContactFetchJob.provider) == "snov",
                col(ContactFetchJob.terminal_state).is_(False),
            )
        ).first()
        if existing_active is not None:
            return

        fetch_job = ContactFetchJob(
            company_id=analysis_job.company_id,
            provider="snov",
            pipeline_run_id=analysis_job.pipeline_run_id,
        )
        session.add(fetch_job)
        session.flush()
        session.add(
            PipelineRunEvent(
                pipeline_run_id=analysis_job.pipeline_run_id,
                company_id=analysis_job.company_id,
                stage=PipelineStage.S3_CONTACTS.value,
                event_type="s2_to_s3_queued",
                payload_json={
                    "analysis_job_id": str(analysis_job.id),
                    "contact_fetch_job_id": str(fetch_job.id),
                    "provider": "snov",
                },
            )
        )
        session.commit()
        from app.tasks.contacts import fetch_contacts

        fetch_contacts.delay(str(fetch_job.id))


def enqueue_s4_for_contact_success(engine: Engine, contact_fetch_job_id: UUID) -> None:
    with Session(engine) as session:
        fetch_job = session.get(ContactFetchJob, contact_fetch_job_id)
        if (
            fetch_job is None
            or fetch_job.pipeline_run_id is None
            or not fetch_job.terminal_state
            or fetch_job.state != ContactFetchJobState.SUCCEEDED
        ):
            return
        contact_ids = [
            str(contact_id)
            for contact_id in session.exec(
                select(ProspectContact.id).where(col(ProspectContact.contact_fetch_job_id) == fetch_job.id)
            ).all()
        ]
        if not contact_ids:
            return

        verify_job = ContactVerifyJob(
            pipeline_run_id=fetch_job.pipeline_run_id,
            state=ContactVerifyJobState.QUEUED,
            terminal_state=False,
            contact_ids_json=contact_ids,
            selected_count=len(contact_ids),
            verified_count=0,
            skipped_count=0,
            filter_snapshot_json={"trigger": "pipeline_orchestrator", "contact_fetch_job_id": str(fetch_job.id)},
        )
        session.add(verify_job)
        session.flush()
        session.add(
            PipelineRunEvent(
                pipeline_run_id=fetch_job.pipeline_run_id,
                company_id=fetch_job.company_id,
                stage=PipelineStage.S4_VALIDATION.value,
                event_type="s3_to_s4_queued",
                payload_json={
                    "contact_fetch_job_id": str(fetch_job.id),
                    "contact_verify_job_id": str(verify_job.id),
                    "selected_count": len(contact_ids),
                },
            )
        )
        session.commit()
        from app.tasks.contacts import verify_contacts_batch

        verify_contacts_batch.delay(str(verify_job.id))
