from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from sqlmodel import Session, select

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import fetch_contacts_selected
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.contacts import BulkContactFetchRequest
from app.models import Company, ContactFetchBatch, Upload
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


def test_bulk_fetch_snov_queues_summary_job_and_batch(sqlite_session: Session) -> None:
    campaign_id, company = _company(sqlite_session, domain="snov.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id], source="snov"),
            session=sqlite_session,
        )

    assert result.queued_count == 1
    assert result.already_fetching_count == 0
    assert result.batch_id is not None
    mock_dispatch.assert_called_once()

    jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(ContactFetchJob.company_id == company.id)
        )
    )
    assert len(jobs) == 1
    assert jobs[0].provider == "snov"
    assert jobs[0].requested_providers_json == ["snov"]
    assert jobs[0].contact_fetch_batch_id == result.batch_id

    batch = sqlite_session.get(ContactFetchBatch, result.batch_id)
    assert batch is not None
    assert batch.requested_provider_mode == "snov"
    assert batch.requested_count == 1
    assert batch.queued_count == 1


def test_bulk_fetch_apollo_queues_summary_job_and_batch(sqlite_session: Session) -> None:
    campaign_id, company = _company(sqlite_session, domain="apollo.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id], source="apollo"),
            session=sqlite_session,
        )

    assert result.queued_count == 1
    assert result.batch_id is not None
    mock_dispatch.assert_called_once()

    job = sqlite_session.exec(
        select(ContactFetchJob).where(ContactFetchJob.company_id == company.id)
    ).one()
    assert job.provider == "apollo"
    assert job.requested_providers_json == ["apollo"]


def test_bulk_fetch_both_creates_one_summary_job_with_two_requested_providers(sqlite_session: Session) -> None:
    campaign_id, company = _company(sqlite_session, domain="both.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id], source="both"),
            session=sqlite_session,
        )

    assert result.queued_count == 1
    assert result.batch_id is not None
    mock_dispatch.assert_called_once()

    jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(ContactFetchJob.company_id == company.id)
        )
    )
    assert len(jobs) == 1
    assert jobs[0].provider == "snov"
    assert jobs[0].requested_providers_json == ["snov", "apollo"]
    assert jobs[0].next_provider is None

    batch = sqlite_session.get(ContactFetchBatch, result.batch_id)
    assert batch is not None
    assert batch.requested_provider_mode == "both"


def test_bulk_fetch_allows_non_contact_ready(sqlite_session: Session) -> None:
    campaign_id, company = _company(sqlite_session, domain="skip.example", stage=CompanyPipelineStage.UPLOADED)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id], source="snov"),
            session=sqlite_session,
        )

    assert result.queued_count == 1
    mock_dispatch.assert_called_once()


def test_bulk_fetch_counts_active_job_as_already_fetching(sqlite_session: Session) -> None:
    campaign_id, company = _company(sqlite_session, domain="active.example", stage=CompanyPipelineStage.CONTACT_READY)
    active = ContactFetchJob(company_id=company.id, provider="snov", terminal_state=False)
    sqlite_session.add(active)
    sqlite_session.commit()

    with patch("app.tasks.contacts.dispatch_contact_fetch_jobs.delay") as mock_dispatch:
        result = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[company.id], source="both"),
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
                BulkContactFetchRequest(campaign_id=campaign.id, company_ids=[uuid4()], source="snov"),
                session=sqlite_session,
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Expected HTTPException")
    mock_dispatch.assert_not_called()
