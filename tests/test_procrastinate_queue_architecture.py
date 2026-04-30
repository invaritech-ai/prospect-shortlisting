from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.scrape import ScrapePageContentRead
from app.api.schemas.upload import CompanyScrapeRequest, CompanyScrapeResult
from app.models import Company, ScrapePage, Upload
from app.models.pipeline import CompanyPipelineStage


def _seed_upload(session: Session, *, campaign_id) -> Upload:
    upload = Upload(
        campaign_id=campaign_id,
        filename="queue-architecture.csv",
        checksum=str(uuid4()),
        row_count=2,
        valid_count=2,
        invalid_count=0,
    )
    session.add(upload)
    session.flush()
    return upload


def _seed_company(session: Session, *, upload_id, domain: str) -> Company:
    company = Company(
        upload_id=upload_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=CompanyPipelineStage.UPLOADED,
    )
    session.add(company)
    session.flush()
    return company


def test_queue_import_paths_include_all_worker_tasks() -> None:
    from app.queue import app

    assert app.import_paths == [
        "app.jobs.health",
        "app.jobs.scrape",
        "app.jobs.ai_decision",
        "app.jobs.contact_fetch",
        "app.jobs.email_reveal",
        "app.jobs.validation",
    ]


def test_company_scrape_result_exposes_backpressure_metadata() -> None:
    result = CompanyScrapeResult(
        requested_count=3,
        queued_count=1,
        skipped_count=2,
        queue_depth=300,
        queued_job_ids=[uuid4()],
        failed_company_ids=[uuid4(), uuid4()],
    )

    assert result.skipped_count == 2
    assert result.queue_depth == 300


def test_scrape_page_content_read_contains_page_metadata() -> None:
    page = ScrapePage(
        id=1,
        job_id=uuid4(),
        url="https://example.com/about",
        canonical_url="https://example.com/about",
        page_kind="about",
        fetch_mode="static",
        status_code=200,
        title="About",
        description="Company profile",
        markdown_content="# About",
        fetch_error_code="",
    )

    read = ScrapePageContentRead.model_validate(page, from_attributes=True)

    assert read.canonical_url == "https://example.com/about"
    assert read.fetch_mode == "static"
    assert read.title == "About"
    assert read.description == "Company profile"
    assert read.created_at == page.created_at


@pytest.mark.asyncio
async def test_scrape_selected_respects_available_queue_slots(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import companies as companies_route

    campaign = create_campaign(payload=CampaignCreate(name="Scrape Queue"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, campaign_id=campaign.id)
    first = _seed_company(sqlite_session, upload_id=upload.id, domain="alpha.example")
    second = _seed_company(sqlite_session, upload_id=upload.id, domain="beta.example")
    sqlite_session.commit()

    deferred: list[dict] = []

    async def fake_defer_async(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(companies_route, "get_engine", lambda: sqlite_session.get_bind())
    monkeypatch.setattr(companies_route, "available_slots", lambda _engine, _queue, _requested: 1)
    monkeypatch.setattr(companies_route, "current_depth", lambda _engine, _queue: 299)
    monkeypatch.setattr(companies_route.scrape_website, "defer_async", fake_defer_async)

    result = await companies_route.scrape_selected_companies(
        payload=CompanyScrapeRequest(
            campaign_id=campaign.id,
            upload_id=upload.id,
            company_ids=[first.id, second.id],
        ),
        session=sqlite_session,
    )

    assert result.requested_count == 2
    assert result.queued_count == 1
    assert result.skipped_count == 1
    assert result.queue_depth == 299
    assert result.failed_company_ids == [second.id]
    assert deferred[0]["priority"] == 75
