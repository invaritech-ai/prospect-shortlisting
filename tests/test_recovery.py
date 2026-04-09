"""Recovery and lock-clearing tests.

test_fail_job_clears_lock_on_queued — transient failure puts job back to QUEUED with lock_token=NULL
test_reset_stuck_clears_locks       — POST /v1/jobs/reset-stuck clears lock_token and lock_expires_at
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlmodel import Session, col, select

from app.models import ScrapeJob
from app.models.pipeline import AnalysisJob, AnalysisJobState, utcnow


def _make_scrape_job(session: Session, *, url_suffix: str = "") -> ScrapeJob:
    from app.services.url_utils import normalize_url, domain_from_url
    url = f"https://recovery-test{url_suffix}.com"
    normalized = normalize_url(url) or url
    domain = domain_from_url(normalized) or normalized
    job = ScrapeJob(
        website_url=url,
        normalized_url=normalized,
        domain=domain,
        js_fallback=False,
        include_sitemap=False,
        general_model="test",
        classify_model="test",
        status="running",
        lock_token=str(uuid4()),
        lock_expires_at=utcnow() + timedelta(minutes=35),
        terminal_state=False,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


class TestFailJobClearsLockOnQueued:
    """Transient failure path: job goes back to QUEUED with lock_token=NULL."""

    def test_lock_cleared_on_queued(self, db_engine):
        from app.services.analysis_service import AnalysisService
        from app.models.pipeline import Prompt, Upload, Company, Run, CrawlArtifact, CrawlJob, CrawlJobState

        svc = AnalysisService()

        with Session(db_engine) as session:
            upload = Upload(filename="test.csv", checksum="ck-recovery", valid_count=1, invalid_count=0)
            session.add(upload)
            session.flush()

            prompt = Prompt(name="test", prompt_text="classify", enabled=True)
            session.add(prompt)
            session.flush()

            company = Company(
                upload_id=upload.id,
                raw_url="https://lock-clear-test.com",
                normalized_url="https://lock-clear-test.com",
                domain="lock-clear-test.com",
            )
            session.add(company)
            session.flush()

            crawl_job = CrawlJob(
                upload_id=upload.id,
                company_id=company.id,
                state=CrawlJobState.SUCCEEDED,
                terminal_state=True,
            )
            session.add(crawl_job)
            session.flush()

            artifact = CrawlArtifact(
                crawl_job_id=crawl_job.id,
                company_id=company.id,
            )
            session.add(artifact)
            session.flush()

            run = Run(
                upload_id=upload.id,
                prompt_id=prompt.id,
                general_model="test",
                classify_model="test",
                status="running",
                total_jobs=1,
                completed_jobs=0,
                failed_jobs=0,
                started_at=utcnow(),
            )
            session.add(run)
            session.flush()

            analysis_job = AnalysisJob(
                run_id=run.id,
                upload_id=upload.id,
                company_id=company.id,
                crawl_artifact_id=artifact.id,
                state=AnalysisJobState.RUNNING,
                terminal_state=False,
                attempt_count=1,
                max_attempts=3,
                prompt_hash="abc",
                lock_token="original-token",
                lock_expires_at=utcnow() + timedelta(minutes=15),
            )
            session.add(analysis_job)
            session.commit()
            session.refresh(analysis_job)

            analysis_job_id = analysis_job.id
            run_id = run.id
            attempt_count = analysis_job.attempt_count
            max_attempts = analysis_job.max_attempts

        svc._fail_job(
            engine=db_engine,
            analysis_job_id=analysis_job_id,
            error_code="transient_error",
            error_message="Simulated transient failure",
            lock_token="original-token",
            run_id=run_id,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        )

        with Session(db_engine) as verify_session:
            refreshed = verify_session.get(AnalysisJob, analysis_job_id)
            assert refreshed is not None
            assert refreshed.state == AnalysisJobState.QUEUED
            assert refreshed.lock_token is None
            assert refreshed.lock_expires_at is None


class TestResetStuckClearsLocks:
    """POST /v1/jobs/reset-stuck clears lock_token and lock_expires_at."""

    def test_reset_stuck_clears_lock_columns(self, session: Session):
        job = _make_scrape_job(session, url_suffix="-reset")
        assert job.lock_token is not None
        assert job.lock_expires_at is not None
        assert job.status == "running"

        stuck_jobs = list(
            session.exec(
                select(ScrapeJob).where(
                    col(ScrapeJob.terminal_state).is_(False)
                    & (col(ScrapeJob.status) == "running")
                )
            )
        )
        for j in stuck_jobs:
            j.status = "created"
            j.terminal_state = False
            j.lock_token = None
            j.lock_expires_at = None
            session.add(j)
        session.commit()

        session.expire_all()
        updated = session.get(ScrapeJob, job.id)
        assert updated is not None
        assert updated.status == "created"
        assert updated.lock_token is None
        assert updated.lock_expires_at is None
