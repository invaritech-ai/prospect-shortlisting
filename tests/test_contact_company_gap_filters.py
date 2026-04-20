from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.routes.contacts import list_contacts_by_company
from app.api.schemas.campaign import CampaignCreate
from app.models import Company, ContactFetchJob, ProspectContact, Upload
from app.models.pipeline import CompanyPipelineStage, ContactFetchJobState


def _seed_company(session: Session, *, domain: str, campaign_id) -> Company:
    upload = Upload(filename="contacts.csv", checksum=str(uuid4()), valid_count=1, invalid_count=0, campaign_id=campaign_id)
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=CompanyPipelineStage.CONTACT_READY,
    )
    session.add(company)
    session.flush()
    return company


def test_contacts_company_gap_filter_and_counters(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Gap Filter Scope"), session=sqlite_session)
    company_a = _seed_company(sqlite_session, domain="no-match.example", campaign_id=campaign.id)
    company_b = _seed_company(sqlite_session, domain="matched-no-email.example", campaign_id=campaign.id)

    fetch_job_a = ContactFetchJob(company_id=company_a.id, provider="snov", state=ContactFetchJobState.SUCCEEDED)
    fetch_job_b = ContactFetchJob(company_id=company_b.id, provider="snov", state=ContactFetchJobState.SUCCEEDED)
    sqlite_session.add(fetch_job_a)
    sqlite_session.add(fetch_job_b)
    sqlite_session.flush()

    sqlite_session.add(
        ProspectContact(
            company_id=company_a.id,
            contact_fetch_job_id=fetch_job_a.id,
            first_name="A",
            last_name="One",
            title="Analyst",
            title_match=False,
            email="a@example.com",
            source="snov",
        )
    )
    sqlite_session.add(
        ProspectContact(
            company_id=company_b.id,
            contact_fetch_job_id=fetch_job_b.id,
            first_name="B",
            last_name="Two",
            title="Head of Growth",
            title_match=True,
            email=None,
            source="snov",
        )
    )
    sqlite_session.commit()

    resp_no_match = list_contacts_by_company(
        campaign_id=campaign.id,
        match_gap_filter="contacts_no_match",
        session=sqlite_session,
    )
    assert len(resp_no_match.items) == 1
    assert resp_no_match.items[0].domain == "no-match.example"
    assert resp_no_match.items[0].unmatched_count == 1
    assert (
        resp_no_match.items[0].last_contact_attempted_at is None
        or isinstance(resp_no_match.items[0].last_contact_attempted_at, datetime)
    )

    resp_no_email = list_contacts_by_company(
        campaign_id=campaign.id,
        match_gap_filter="matched_no_email",
        session=sqlite_session,
    )
    assert len(resp_no_email.items) == 1
    assert resp_no_email.items[0].domain == "matched-no-email.example"
    assert resp_no_email.items[0].matched_no_email_count == 1


def test_contacts_company_last_attempt_is_null_when_missing_jobs(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="No Jobs Scope"), session=sqlite_session)
    company = _seed_company(sqlite_session, domain="no-jobs.example", campaign_id=campaign.id)
    sqlite_session.add(
        ProspectContact(
            company_id=company.id,
            contact_fetch_job_id=uuid4(),
            first_name="C",
            last_name="Three",
            title="Director",
            title_match=True,
            email="c@example.com",
            source="snov",
            created_at=datetime.now(timezone.utc),
        )
    )
    sqlite_session.commit()

    resp = list_contacts_by_company(campaign_id=campaign.id, search="no-jobs.example", session=sqlite_session)
    assert len(resp.items) == 1
    assert resp.items[0].last_contact_attempted_at is None
