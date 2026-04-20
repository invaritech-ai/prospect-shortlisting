from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import fetch_contacts_selected
from app.api.schemas.campaign import CampaignCreate
from app.api.schemas.contacts import BulkContactFetchRequest
from app.models import Company, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJob
from sqlmodel import select


def _company(session: Session, *, domain: str, stage: CompanyPipelineStage):
    campaign = create_campaign(payload=CampaignCreate(name=f"Campaign {domain}"), session=session)
    upload = Upload(filename="t.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0, campaign_id=campaign.id)
    session.add(upload)
    session.flush()
    c = Company(
        upload_id=upload.id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=stage,
    )
    session.add(c)
    session.flush()
    return campaign.id, c


def test_bulk_fetch_snov(sqlite_session: Session) -> None:
    campaign_id, c = _company(sqlite_session, domain="snov.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()
    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock:
        r = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[c.id], source="snov"),
            session=sqlite_session,
        )
    assert r.queued_count == 1
    assert mock.call_count == 1


def test_bulk_fetch_apollo(sqlite_session: Session) -> None:
    campaign_id, c = _company(sqlite_session, domain="apollo.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()
    with patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as mock:
        r = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[c.id], source="apollo"),
            session=sqlite_session,
        )
    assert r.queued_count == 1
    assert mock.call_count == 1


def test_bulk_fetch_both_enqueues_snov_then_apollo_chain(sqlite_session: Session) -> None:
    """source='both' seeds only the snov job with apollo follow-up."""
    campaign_id, c = _company(sqlite_session, domain="both.example", stage=CompanyPipelineStage.CONTACT_READY)
    sqlite_session.commit()
    with (
        patch("app.api.routes.contacts.fetch_contacts.delay") as snov,
        patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as apollo,
    ):
        r = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[c.id], source="both"),
            session=sqlite_session,
        )
    assert r.queued_count == 1
    assert snov.call_count == 1
    assert apollo.call_count == 0
    jobs = list(
        sqlite_session.exec(
            select(ContactFetchJob).where(ContactFetchJob.company_id == c.id).order_by(ContactFetchJob.created_at)
        )
    )
    assert len(jobs) == 1
    assert jobs[0].provider == "snov"
    assert jobs[0].next_provider == "apollo"


def test_bulk_fetch_allows_non_contact_ready(sqlite_session: Session) -> None:
    campaign_id, c = _company(sqlite_session, domain="skip.example", stage=CompanyPipelineStage.UPLOADED)
    sqlite_session.commit()
    with patch("app.api.routes.contacts.fetch_contacts.delay") as mock:
        r = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[c.id], source="snov"),
            session=sqlite_session,
        )
    assert r.queued_count == 1
    assert mock.call_count == 1


def test_bulk_fetch_both_updates_active_snov_job_with_apollo_followup(sqlite_session: Session) -> None:
    campaign_id, c = _company(sqlite_session, domain="both-active.example", stage=CompanyPipelineStage.CONTACT_READY)
    active = ContactFetchJob(company_id=c.id, provider="snov", next_provider=None, terminal_state=False)
    sqlite_session.add(active)
    sqlite_session.commit()
    sqlite_session.refresh(active)

    with (
        patch("app.api.routes.contacts.fetch_contacts.delay") as snov,
        patch("app.api.routes.contacts.fetch_contacts_apollo.delay") as apollo,
    ):
        r = fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign_id, company_ids=[c.id], source="both"),
            session=sqlite_session,
        )

    assert r.queued_count == 0
    assert r.already_fetching_count == 1
    assert snov.call_count == 0
    assert apollo.call_count == 0
    sqlite_session.refresh(active)
    assert active.next_provider == "apollo"


def test_bulk_fetch_missing_ids_raises_404(sqlite_session: Session) -> None:
    from fastapi import HTTPException

    campaign = create_campaign(payload=CampaignCreate(name="Missing IDs"), session=sqlite_session)
    with pytest.raises(HTTPException) as exc:
        fetch_contacts_selected(
            BulkContactFetchRequest(campaign_id=campaign.id, company_ids=[uuid4()], source="snov"),
            session=sqlite_session,
        )
    assert exc.value.status_code == 404
