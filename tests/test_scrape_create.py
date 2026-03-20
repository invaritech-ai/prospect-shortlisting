"""ScrapeService.create_job isolation tests.

Uses in-memory SQLite — no containers, no network.

Tests:
- create_job returns a ScrapeJob with correct fields
- Duplicate active URL raises ScrapeJobAlreadyRunningError
- Terminal (completed/failed) job allows a new job for the same URL
- Invalid URL raises ValueError
"""
from __future__ import annotations

import pytest
from sqlmodel import Session

from app.models import ScrapeJob
from app.services.scrape_service import ScrapeJobAlreadyRunningError, ScrapeService


@pytest.fixture
def svc() -> ScrapeService:
    return ScrapeService()


class TestCreateJob:
    def test_creates_job_with_correct_fields(self, sqlite_session: Session, svc: ScrapeService):
        job = svc.create_job(
            session=sqlite_session,
            website_url="https://example.com",
            js_fallback=True,
            include_sitemap=True,
            general_model="openai/gpt-5-nano",
            classify_model="inception/mercury-2",
        )
        sqlite_session.commit()

        assert job.id is not None
        assert job.status == "created"
        assert job.terminal_state is False
        assert "example.com" in job.normalized_url
        assert job.domain == "example.com"
        assert job.js_fallback is True
        assert job.general_model == "openai/gpt-5-nano"

    def test_normalises_url(self, sqlite_session: Session, svc: ScrapeService):
        job = svc.create_job(
            session=sqlite_session,
            website_url="HTTP://EXAMPLE.COM/",
            js_fallback=False,
            include_sitemap=False,
            general_model="m",
            classify_model="m",
        )
        sqlite_session.commit()
        assert job.normalized_url == job.normalized_url.lower()

    def test_rejects_invalid_url(self, sqlite_session: Session, svc: ScrapeService):
        with pytest.raises(ValueError):
            svc.create_job(
                session=sqlite_session,
                website_url="not-a-url",
                js_fallback=False,
                include_sitemap=False,
                general_model="m",
                classify_model="m",
            )


class TestDuplicateJobRejection:
    def test_active_duplicate_raises(self, sqlite_session: Session, svc: ScrapeService):
        svc.create_job(
            session=sqlite_session,
            website_url="https://dup-test.com",
            js_fallback=False,
            include_sitemap=False,
            general_model="m",
            classify_model="m",
        )
        sqlite_session.commit()

        with pytest.raises(ScrapeJobAlreadyRunningError) as exc_info:
            svc.create_job(
                session=sqlite_session,
                website_url="https://dup-test.com",
                js_fallback=False,
                include_sitemap=False,
                general_model="m",
                classify_model="m",
            )
        assert exc_info.value.existing_job_id is not None

    def test_terminal_job_allows_new_job(self, sqlite_session: Session, svc: ScrapeService):
        # Create and immediately mark as terminal.
        first = svc.create_job(
            session=sqlite_session,
            website_url="https://terminal-test.com",
            js_fallback=False,
            include_sitemap=False,
            general_model="m",
            classify_model="m",
        )
        first.status = "completed"
        first.terminal_state = True
        sqlite_session.add(first)
        sqlite_session.commit()

        # Should now be allowed.
        second = svc.create_job(
            session=sqlite_session,
            website_url="https://terminal-test.com",
            js_fallback=False,
            include_sitemap=False,
            general_model="m",
            classify_model="m",
        )
        sqlite_session.commit()
        assert second.id != first.id
        assert second.status == "created"
