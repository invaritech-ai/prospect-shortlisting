from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.routes.companies import (
    export_companies_csv,
    get_company_counts,
    get_letter_counts,
    list_companies,
    list_company_ids,
)
from app.api.routes.contacts import (
    _select_verification_contact_ids,
    export_contacts_csv,
    fetch_contacts_for_company,
    get_contact_counts,
    list_company_contacts,
    list_all_contacts,
    list_contacts_by_company,
)
from app.api.schemas.contacts import ContactVerifyRequest
from app.api.routes.stats import get_cost_stats, get_stats
from app.api.schemas.campaign import CampaignCreate
from app.models import AiUsageEvent, Company, ContactFetchJob, ProspectContact, Upload
from app.models.pipeline import CompanyPipelineStage


def _seed_upload(session: Session, filename: str, *, campaign_id) -> Upload:
    upload = Upload(
        filename=filename,
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
        campaign_id=campaign_id,
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
        pipeline_stage=CompanyPipelineStage.CONTACT_READY,
    )
    session.add(company)
    session.flush()
    return company


def _seed_contact(session: Session, *, company: Company, email: str) -> None:
    fetch_job = ContactFetchJob(company_id=company.id, provider="snov")
    session.add(fetch_job)
    session.flush()
    contact = ProspectContact(
        company_id=company.id,
        contact_fetch_job_id=fetch_job.id,
        first_name="Sam",
        last_name="Lee",
        title="Director",
        title_match=True,
        email=email,
        source="snov",
        verification_status="unverified",
    )
    contact.updated_at = contact.updated_at - timedelta(days=2)
    session.add(contact)
    session.flush()


def test_company_routes_are_campaign_scoped(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Scoped A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Scoped B"), session=sqlite_session)

    upload_a = _seed_upload(sqlite_session, "a.csv", campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, "b.csv", campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="alpha.example")
    _seed_company(sqlite_session, upload_id=upload_b.id, domain="beta.example")
    sqlite_session.commit()

    rows = list_companies(
        session=sqlite_session,
        campaign_id=campaign_a.id,
        include_total=True,
        limit=25,
        offset=0,
    )
    assert rows.total == 1
    assert [item.domain for item in rows.items] == ["alpha.example"]

    company_ids = list_company_ids(
        session=sqlite_session,
        campaign_id=campaign_a.id,
        decision_filter="all",
        scrape_filter="all",
        stage_filter="all",
    )
    assert company_ids.total == 1
    assert company_ids.ids == [company_a.id]

    letter_counts = get_letter_counts(
        session=sqlite_session,
        campaign_id=campaign_a.id,
        decision_filter="all",
        scrape_filter="all",
        stage_filter="all",
    )
    assert letter_counts.counts["a"] == 1
    assert letter_counts.counts["b"] == 0

    counts = get_company_counts(session=sqlite_session, campaign_id=campaign_a.id)
    assert counts.total == 1
    assert counts.contact_ready == 1

    export_response = export_companies_csv(session=sqlite_session, campaign_id=campaign_a.id)
    assert "alpha.example" in export_response.body.decode("utf-8")
    assert "beta.example" not in export_response.body.decode("utf-8")


def test_contact_and_stats_routes_are_campaign_scoped(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Contacts A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Contacts B"), session=sqlite_session)

    upload_a = _seed_upload(sqlite_session, "contacts-a.csv", campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, "contacts-b.csv", campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="north.example")
    company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="south.example")
    _seed_contact(sqlite_session, company=company_a, email="north@example.com")
    _seed_contact(sqlite_session, company=company_b, email="south@example.com")
    sqlite_session.commit()

    contacts = list_all_contacts(
        session=sqlite_session,
        campaign_id=campaign_a.id,
        stage_filter="all",
        limit=50,
        offset=0,
    )
    assert contacts.total == 1
    assert [item.domain for item in contacts.items] == ["north.example"]
    letters = list_all_contacts(
        session=sqlite_session,
        campaign_id=campaign_a.id,
        stage_filter="all",
        count_by_letters=True,
        limit=50,
        offset=0,
    )
    assert letters.letter_counts is not None
    assert letters.letter_counts["n"] == 1
    assert letters.letter_counts["s"] == 0

    by_company = list_contacts_by_company(
        session=sqlite_session,
        campaign_id=campaign_a.id,
        stage_filter="all",
        limit=50,
        offset=0,
    )
    assert by_company.total == 1
    assert [item.domain for item in by_company.items] == ["north.example"]
    company_contacts = list_company_contacts(session=sqlite_session, campaign_id=campaign_a.id, company_id=company_a.id)
    assert company_contacts.total == 1

    contact_counts = get_contact_counts(session=sqlite_session, campaign_id=campaign_a.id)
    assert contact_counts.total == 1
    assert contact_counts.eligible_verify == 1

    stats = get_stats(session=sqlite_session, campaign_id=campaign_a.id)
    assert stats.validation.total == 0
    assert stats.contact_fetch.total == 1

    sqlite_session.add(
        AiUsageEvent(
            campaign_id=campaign_a.id,
            company_id=company_a.id,
            stage="s2_analysis",
            billed_cost_usd=Decimal("0.0123"),
        )
    )
    sqlite_session.commit()
    cost_rows = get_cost_stats(session=sqlite_session, campaign_id=campaign_a.id, limit=50, offset=0)
    assert cost_rows.total == 1
    assert [item.domain for item in cost_rows.items] == ["north.example"]
    export_response = export_contacts_csv(session=sqlite_session, campaign_id=campaign_a.id)
    export_text = export_response.body.decode("utf-8")
    assert "north.example" in export_text
    assert "south.example" not in export_text


def test_stats_upload_scope_errors_are_explicit(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Stats Error A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Stats Error B"), session=sqlite_session)
    upload_b = _seed_upload(sqlite_session, "other.csv", campaign_id=campaign_b.id)
    sqlite_session.commit()

    with pytest.raises(HTTPException) as missing_exc:
        get_stats(session=sqlite_session, campaign_id=campaign_a.id, upload_id=uuid4())
    assert missing_exc.value.status_code == 404

    with pytest.raises(HTTPException) as mismatch_exc:
        get_stats(session=sqlite_session, campaign_id=campaign_a.id, upload_id=upload_b.id)
    assert mismatch_exc.value.status_code == 422

    with pytest.raises(HTTPException) as contacts_scope_exc:
        list_company_contacts(session=sqlite_session, campaign_id=campaign_a.id, company_id=_seed_company(sqlite_session, upload_id=upload_b.id, domain="wrong.example").id)
    assert contacts_scope_exc.value.status_code == 422


def test_contact_routes_missing_campaign_raise_404(sqlite_session: Session) -> None:
    missing_campaign_id = uuid4()

    with pytest.raises(HTTPException) as contacts_exc:
        list_all_contacts(
            session=sqlite_session,
            campaign_id=missing_campaign_id,
            stage_filter="all",
            limit=50,
            offset=0,
        )
    assert contacts_exc.value.status_code == 404

    with pytest.raises(HTTPException) as by_company_exc:
        list_contacts_by_company(
            session=sqlite_session,
            campaign_id=missing_campaign_id,
            stage_filter="all",
            limit=50,
            offset=0,
        )
    assert by_company_exc.value.status_code == 404

    with pytest.raises(HTTPException) as counts_exc:
        get_contact_counts(session=sqlite_session, campaign_id=missing_campaign_id)
    assert counts_exc.value.status_code == 404

    with pytest.raises(HTTPException) as export_exc:
        export_contacts_csv(session=sqlite_session, campaign_id=missing_campaign_id)
    assert export_exc.value.status_code == 404


def test_contact_fetch_and_company_contacts_missing_campaign_raise_404(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Missing Campaign Contacts"), session=sqlite_session)
    upload = _seed_upload(sqlite_session, "missing-campaign.csv", campaign_id=campaign.id)
    company = _seed_company(sqlite_session, upload_id=upload.id, domain="missing-campaign.example")
    _seed_contact(sqlite_session, company=company, email="x@missing-campaign.example")
    sqlite_session.commit()

    with pytest.raises(HTTPException) as fetch_exc:
        fetch_contacts_for_company(company_id=company.id, campaign_id=uuid4(), session=sqlite_session)
    assert fetch_exc.value.status_code == 404

    with pytest.raises(HTTPException) as company_contacts_exc:
        list_company_contacts(company_id=company.id, campaign_id=uuid4(), session=sqlite_session)
    assert company_contacts_exc.value.status_code == 404


def test_verify_selection_is_campaign_scoped(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Verify A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Verify B"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, "verify-a.csv", campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, "verify-b.csv", campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="verify-a.example")
    company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="verify-b.example")
    _seed_contact(sqlite_session, company=company_a, email="a@verify.example")
    _seed_contact(sqlite_session, company=company_b, email="b@verify.example")
    sqlite_session.commit()

    selected = _select_verification_contact_ids(
        sqlite_session,
        ContactVerifyRequest(campaign_id=campaign_a.id, search="verify.example"),
    )
    assert len(selected) == 1
