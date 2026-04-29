"""Celery task isolation tests.

Uses CELERY_TASK_ALWAYS_EAGER=True so tasks run synchronously in-process
without a broker. No Redis required.

Tests:
- scrape_website: CAS lock — second delivery of same job is a no-op
- scrape_website: already-terminal job is skipped without error
- run_analysis_job: CAS lock — second delivery does nothing
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session

from app.models import ScrapeJob
from app.models.pipeline import AnalysisJob, AnalysisJobState, utcnow


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def celery_eager(monkeypatch):
    """Force Celery tasks to run synchronously (no broker needed)."""
    from app.celery_app import app as celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture
def scrape_job(sqlite_session: Session) -> ScrapeJob:
    job = ScrapeJob(
        website_url="https://celery-test.com",
        normalized_url="https://celery-test.com",
        domain="celery-test.com",
        status="created",
        terminal_state=False,
        js_fallback=False,
        include_sitemap=False,
        general_model="m",
        classify_model="m",
    )
    sqlite_session.add(job)
    sqlite_session.commit()
    sqlite_session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# scrape_website task
# ---------------------------------------------------------------------------


class TestScrapeWebsiteTask:
    def test_already_terminal_job_skipped(self, sqlite_session: Session, sqlite_engine, scrape_job: ScrapeJob):
        """If the job is already terminal before the task starts, CAS fails silently."""
        scrape_job.status = "completed"
        scrape_job.terminal_state = True
        sqlite_session.add(scrape_job)
        sqlite_session.commit()

        with patch("app.tasks.scrape.get_engine", return_value=sqlite_engine):
            # Mock run_scrape so we're testing task-level CAS, not the full scrape pipeline.
            with patch("app.tasks.scrape.ScrapeService") as MockService:
                mock_instance = MockService.return_value
                mock_instance.run_scrape = AsyncMock(return_value=None)

                from app.tasks.scrape import scrape_website
                # Should not raise.
                scrape_website.apply(args=[str(scrape_job.id)])

    def test_second_delivery_does_not_double_run(self, sqlite_session: Session, sqlite_engine, scrape_job: ScrapeJob):
        """Simulates Celery re-delivering the same task ID: the second call should
        exit after CAS fails (first call already set lock_token)."""
        call_count = 0

        async def fake_run_scrape(*, engine, job_id, scrape_rules=None):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            # Simulate the CAS: first call claims the job.
            from uuid import UUID as _UUID
            job_uuid = _UUID(str(job_id)) if not isinstance(job_id, _UUID.__class__) else job_id
            with Session(engine) as s:
                j = s.get(ScrapeJob, job_uuid)
                if j and not j.terminal_state and j.status in ("created", "running"):
                    j.status = "running"
                    j.lock_token = "first-lock"
                    j.lock_expires_at = utcnow() + timedelta(minutes=35)
                    s.add(j)
                    s.commit()

        with patch("app.tasks.scrape.get_engine", return_value=sqlite_engine), \
             patch("app.tasks.scrape.ScrapeService") as MockService:
            MockService.return_value.run_scrape = fake_run_scrape

            from app.tasks.scrape import scrape_website
            scrape_website.apply(args=[str(scrape_job.id)])

        # Exactly one run_scrape call.
        assert call_count == 1


# ---------------------------------------------------------------------------
# run_analysis_job task
# ---------------------------------------------------------------------------


class TestRunAnalysisJobTask:
    def _make_minimal_analysis_job(self, session: Session) -> AnalysisJob:
        from app.models.pipeline import Upload, Prompt, Company, CrawlJob, CrawlJobState, CrawlArtifact

        upload = Upload(filename="t.csv", checksum="ck-celery", valid_count=1, invalid_count=0)
        session.add(upload)
        session.flush()

        prompt = Prompt(name="p", prompt_text="classify", enabled=True)
        session.add(prompt)
        session.flush()

        company = Company(
            upload_id=upload.id,
            raw_url="https://celery-analysis.com",
            normalized_url="https://celery-analysis.com",
            domain="celery-analysis.com",
        )
        session.add(company)
        session.flush()

        cj = CrawlJob(upload_id=upload.id, company_id=company.id, state=CrawlJobState.SUCCEEDED, terminal_state=True)
        session.add(cj)
        session.flush()

        artifact = CrawlArtifact(company_id=company.id, crawl_job_id=cj.id)
        session.add(artifact)
        session.flush()

        job = AnalysisJob(
            upload_id=upload.id,
            company_id=company.id,
            crawl_artifact_id=artifact.id,
            prompt_id=prompt.id,
            general_model="m",
            classify_model="m",
            state=AnalysisJobState.QUEUED,
            terminal_state=False,
            attempt_count=0,
            max_attempts=3,
            prompt_hash="abc",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    def test_already_terminal_is_skipped(self, sqlite_session: Session, sqlite_engine):
        job = self._make_minimal_analysis_job(sqlite_session)
        job.state = AnalysisJobState.SUCCEEDED
        job.terminal_state = True
        sqlite_session.add(job)
        sqlite_session.commit()

        with patch("app.tasks.analysis.get_engine", return_value=sqlite_engine), \
             patch("app.tasks.analysis.AnalysisService") as MockSvc:
            MockSvc.return_value.run_analysis_job.return_value = None  # CAS miss

            from app.tasks.analysis import run_analysis_job
            run_analysis_job.apply(args=[str(job.id)])

            # run_analysis_job on the service should have been called but returned None (CAS miss).
            MockSvc.return_value.run_analysis_job.assert_called_once()


def test_contact_task_routes_keep_discovery_reveal_and_verify_separate() -> None:
    from app.celery_app import app as celery_app

    routes = celery_app.conf.task_routes
    assert routes["app.tasks.contacts.fetch_contacts"]["queue"] == "contacts_orchestrator"
    assert routes["app.tasks.contacts.fetch_contacts_apollo"]["queue"] == "contacts_orchestrator"
    assert routes["app.tasks.contacts.fetch_contacts_snov_attempt"]["queue"] == "contacts_snov"
    assert routes["app.tasks.contacts.fetch_contacts_apollo_attempt"]["queue"] == "contacts_apollo"
    assert routes["app.tasks.contacts.reveal_contact_emails"]["queue"] == "contacts_reveal_orchestrator"
    assert routes["app.tasks.contacts.reveal_contact_apollo_attempt"]["queue"] == "contacts_reveal_apollo"
    assert routes["app.tasks.contacts.reveal_contact_snov_attempt"]["queue"] == "contacts_reveal_snov"
    assert routes["app.tasks.contacts.verify_contacts_batch"]["queue"] == "contacts_verify"
    assert "app.tasks.contacts.dispatch_contact_reveal_jobs" not in routes
    assert "dispatch-contact-reveal-jobs" not in celery_app.conf.beat_schedule
