from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, select

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import fetch_contacts_selected
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.contacts import BulkContactFetchRequest
from app.models import Company, ContactFetchBatch, DiscoveredContact, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJob


def _company(session: Session, *, domain: str, stage: CompanyPipelineStage):
    campaign = create_campaign(payload=CampaignCreate(name=f"Campaign {domain}"), session=session)
    upload = Upload(filename="t.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0, campaign_id=campaign.id)
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=stage,
    )
    session.add(company)
    session.flush()
    return campaign.id, company


def test_bulk_fetch_queues_both_providers(sqlite_session: Session) -> None:
    campaign_id, company = _company(sqlite_session, domain="both.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id]),
            session=sqlite_session,
        )

    assert result.queued_count == 1
    assert result.already_fetching_count == 0
    assert result.batch_id is not None
    mock_dispatch.assert_called_once()

    job = sqlite_session.exec(
        select(ContactFetchJob).where(ContactFetchJob.company_id == company.id)
    ).one()
    assert job.provider == "snov"
    assert job.requested_providers_json == ["snov", "apollo"]
    assert job.contact_fetch_batch_id == result.batch_id

    batch = sqlite_session.get(ContactFetchBatch, result.batch_id)
    assert batch is not None
    assert batch.requested_provider_mode == "both"
    assert batch.requested_count == 1
    assert batch.queued_count == 1


def test_bulk_fetch_reuses_fresh_cache(sqlite_session: Session, monkeypatch) -> None:
    aware_now = datetime.now(timezone.utc)
    monkeypatch.setattr("app.services.contact_queue_service.utcnow", lambda: aware_now)

    campaign_id, company = _company(sqlite_session, domain="fresh.example", stage=CompanyPipelineStage.CONTACT_READY)
    for provider in ("snov", "apollo"):
        sqlite_session.add(
            DiscoveredContact(
                company_id=company.id,
                provider=provider,
                provider_person_id=f"pid-{provider}",
                first_name="Test",
                last_name="Person",
                last_seen_at=aware_now,
            )
        )
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id]),
            session=sqlite_session,
        )

    assert result.queued_count == 0
    assert result.reused_count == 1
    mock_dispatch.assert_called_once()


def test_bulk_fetch_force_refresh_skips_fresh_cache(sqlite_session: Session, monkeypatch) -> None:
    aware_now = datetime.now(timezone.utc)
    monkeypatch.setattr("app.services.contact_queue_service.utcnow", lambda: aware_now)

    campaign_id, company = _company(sqlite_session, domain="refresh.example", stage=CompanyPipelineStage.CONTACT_READY)
    for provider in ("snov", "apollo"):
        sqlite_session.add(
            DiscoveredContact(
                company_id=company.id,
                provider=provider,
                provider_person_id=f"pid-{provider}",
                first_name="Test",
                last_name="Person",
                last_seen_at=aware_now,
            )
        )
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id], force_refresh=True),
            session=sqlite_session,
        )

    assert result.queued_count == 1
    assert result.reused_count == 0
    mock_dispatch.assert_called_once()


def test_bulk_fetch_counts_active_job_as_already_fetching(sqlite_session: Session) -> None:
    campaign_id, company = _company(sqlite_session, domain="active.example", stage=CompanyPipelineStage.CONTACT_READY)
    active = ContactFetchJob(company_id=company.id, provider="snov", terminal_state=False)
    sqlite_session.add(active)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id]),
            session=sqlite_session,
        )

    assert result.requested_count == 1
    assert result.queued_count == 0
    assert result.already_fetching_count == 1
    mock_dispatch.assert_called_once()

    jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(ContactFetchJob.company_id == company.id)
        )
    )
    assert len(jobs) == 1
    assert jobs[0].id == active.id


def test_bulk_fetch_missing_ids_raises_404(sqlite_session: Session) -> None:
    from fastapi import HTTPException

    campaign = create_campaign(payload=CampaignCreate(name="Missing IDs"), session=sqlite_session)
    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        try:
            fetch_contacts_selected(
                BulkContactFetchRequest(campaign_id=campaign.id, company_ids=[uuid4()]),
                session=sqlite_session,
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Expected HTTPException")
    mock_dispatch.assert_not_called()
