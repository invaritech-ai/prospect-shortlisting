"""Run lifecycle: create analysis runs + refresh run completion status."""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case as sa_case
from sqlmodel import Session, col, func, select

from app.core.logging import log_event
from app.models import (
    AnalysisJob,
    Company,
    Prompt,
    Run,
)
from app.models.pipeline import AnalysisJobState, RunStatus
from app.services.context_service import bulk_ensure_crawl_adapters, bulk_latest_completed_scrape_jobs


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunService:
    def create_runs(
        self,
        *,
        session: Session,
        companies: list[Company],
        prompt_id: UUID,
        general_model: str,
        classify_model: str,
        pipeline_run_id: UUID | None = None,
    ) -> tuple[list[Run], list[AnalysisJob], list[UUID]]:
        prompt = session.get(Prompt, prompt_id)
        if not prompt:
            raise ValueError("Prompt not found.")
        if not prompt.enabled:
            raise ValueError("Selected prompt is disabled.")

        grouped: dict[UUID, list[Company]] = {}
        skipped_company_ids: list[UUID] = []
        queued_runs: list[Run] = []
        queued_jobs: list[AnalysisJob] = []

        # ── Bulk pre-fetch pass ──────────────────────────────────────────────
        all_urls = [c.normalized_url for c in companies if c.normalized_url]
        scrape_map = bulk_latest_completed_scrape_jobs(session=session, normalized_urls=all_urls)

        for company in companies:
            if scrape_map.get(company.normalized_url) is None:
                skipped_company_ids.append(company.id)
                continue
            grouped.setdefault(company.upload_id, []).append(company)

        active_companies = [c for groups in grouped.values() for c in groups]

        artifact_map = bulk_ensure_crawl_adapters(
            session=session, companies=active_companies, scrape_map=scrape_map
        )

        prompt_hash = hashlib.sha256(prompt.prompt_text.encode("utf-8")).hexdigest()
        for upload_id, grouped_companies in grouped.items():
            run = Run(
                upload_id=upload_id,
                prompt_id=prompt.id,
                general_model=general_model,
                classify_model=classify_model,
                status=RunStatus.RUNNING,
                total_jobs=0,
                completed_jobs=0,
                failed_jobs=0,
                started_at=utcnow(),
            )
            session.add(run)
            session.flush()  # needed for run.id FK in AnalysisJob

            for company in grouped_companies:
                artifact = artifact_map.get(company.id)
                if artifact is None:
                    skipped_company_ids.append(company.id)
                    continue
                queued_jobs.append(AnalysisJob(
                    run_id=run.id,
                    pipeline_run_id=pipeline_run_id,
                    upload_id=company.upload_id,
                    company_id=company.id,
                    crawl_artifact_id=artifact.id,
                    state=AnalysisJobState.QUEUED,
                    terminal_state=False,
                    prompt_hash=prompt_hash,
                ))
            queued_runs.append(run)

        # Count jobs per run in one pass.
        jobs_per_run: dict[UUID, int] = defaultdict(int)
        for job in queued_jobs:
            jobs_per_run[job.run_id] += 1
        for run in queued_runs:
            run.total_jobs = jobs_per_run[run.id]

        session.add_all(queued_jobs)
        session.flush()
        for run in queued_runs:
            session.refresh(run)
        for job in queued_jobs:
            session.refresh(job)
        return queued_runs, queued_jobs, skipped_company_ids

    def refresh_run_status(self, *, session: Session, run_id: UUID) -> None:
        run = session.get(Run, run_id)
        if not run or run.total_jobs == 0:
            return

        row = session.exec(
            select(
                func.count(sa_case((col(AnalysisJob.state) == AnalysisJobState.SUCCEEDED, 1))).label("succeeded"),
                func.count(sa_case((col(AnalysisJob.state).in_([AnalysisJobState.FAILED, AnalysisJobState.DEAD]), 1))).label("failed"),
                func.count(sa_case((col(AnalysisJob.terminal_state).is_(True), 1))).label("terminal"),
            )
            .select_from(AnalysisJob)
            .where(col(AnalysisJob.run_id) == run_id)
        ).one()
        succeeded = row.succeeded or 0
        failed = row.failed or 0
        terminal = row.terminal or 0

        run.completed_jobs = succeeded
        run.failed_jobs = failed
        is_done = terminal >= run.total_jobs
        if is_done:
            run.status = RunStatus.FAILED if failed > 0 else RunStatus.COMPLETED
            if not run.finished_at:
                run.finished_at = utcnow()
        else:
            run.status = RunStatus.RUNNING
        session.add(run)
        session.commit()
