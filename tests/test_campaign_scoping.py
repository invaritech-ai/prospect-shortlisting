from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.routes.companies import delete_companies, list_companies
from app.api.routes.contacts import list_all_contacts
from app.api.routes.runs import create_runs
from app.api.routes.scrape_actions import scrape_selected_companies
from app.api.schemas.run import RunCreateRequest
from app.api.schemas.upload import CompanyDeleteRequest, CompanyScrapeRequest
from app.api.routes.stats import get_company_counts, get_cost_stats, get_stats
from app.tasks import company as company_tasks
from app.api.schemas.campaign import CampaignCreate
from app.models import AiUsageEvent, Company, ContactFetchJob, Prompt, ProspectContact, Upload
from app.models.pipeline import CompanyPipelineStage


def _list_companies(session: Session, *, campaign_id, **overrides):
    params = {
        "session": session,
        "campaign_id": campaign_id,
        "limit": 25,
        "offset": 0,
        "decision_filter": "all",
        "scrape_filter": "all",
        "include_total": False,
        "letter": None,
        "letters": None,
        "stage_filter": "all",
        "status_filter": "all",
        "search": None,
        "sort_by": "last_activity",
        "sort_dir": "desc",
        "upload_id": None,
    }
    params.update(overrides)
    return list_companies(**params)


def _get_company_counts(session: Session, *, campaign_id, upload_id=None):
    return get_company_counts(session=session, campaign_id=campaign_id, upload_id=upload_id)


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
    _seed_company(sqlite_session, upload_id=upload_a.id, domain="alpha.example")
    _seed_company(sqlite_session, upload_id=upload_b.id, domain="beta.example")
    sqlite_session.commit()

    rows = _list_companies(
        session=sqlite_session,
        campaign_id=campaign_a.id,
        include_total=True,
        limit=25,
        offset=0,
    )
    assert rows.total == 1
    assert [item.domain for item in rows.items] == ["alpha.example"]

    counts = _get_company_counts(session=sqlite_session, campaign_id=campaign_a.id)
    assert counts.total == 1
    assert counts.contact_ready == 1


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



def test_delete_companies_is_campaign_scoped(sqlite_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Delete A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Delete B"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, "delete-a.csv", campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, "delete-b.csv", campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="delete-a.example")
    company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="delete-b.example")
    sqlite_session.commit()

    captured: dict[str, object] = {}

    def fake_delay(*, company_ids: list[str], campaign_id: str) -> None:
        captured["company_ids"] = company_ids
        captured["campaign_id"] = campaign_id

    monkeypatch.setattr(company_tasks.cascade_delete_companies, "delay", fake_delay)

    result = delete_companies(
        payload=CompanyDeleteRequest(campaign_id=campaign_a.id, company_ids=[company_a.id, company_b.id]),
        session=sqlite_session,
    )

    assert result.queued_ids == [company_a.id]
    assert result.queued_count == 1
    assert captured == {
        "company_ids": [str(company_a.id)],
        "campaign_id": str(campaign_a.id),
    }
    assert sqlite_session.get(Company, company_a.id) is not None
    assert sqlite_session.get(Company, company_b.id) is not None


def test_scrape_selected_rejects_company_ids_outside_campaign(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Scrape A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Scrape B"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, "scrape-a.csv", campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, "scrape-b.csv", campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="scrape-a.example")
    company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="scrape-b.example")
    sqlite_session.commit()

    with pytest.raises(HTTPException) as exc:
        scrape_selected_companies(
            payload=CompanyScrapeRequest(campaign_id=campaign_a.id, company_ids=[company_a.id, company_b.id]),
            session=sqlite_session,
            x_idempotency_key=None,
        )
    assert exc.value.status_code == 422


def test_create_runs_rejects_company_ids_outside_campaign(sqlite_session: Session) -> None:
    campaign_a = create_campaign(payload=CampaignCreate(name="Runs A"), session=sqlite_session)
    campaign_b = create_campaign(payload=CampaignCreate(name="Runs B"), session=sqlite_session)
    upload_a = _seed_upload(sqlite_session, "runs-a.csv", campaign_id=campaign_a.id)
    upload_b = _seed_upload(sqlite_session, "runs-b.csv", campaign_id=campaign_b.id)
    company_a = _seed_company(sqlite_session, upload_id=upload_a.id, domain="runs-a.example")
    company_b = _seed_company(sqlite_session, upload_id=upload_b.id, domain="runs-b.example")
    company_a.pipeline_stage = CompanyPipelineStage.SCRAPED
    company_b.pipeline_stage = CompanyPipelineStage.SCRAPED
    sqlite_session.add(company_a)
    sqlite_session.add(company_b)
    prompt = Prompt(name="Scoped Prompt", enabled=True, prompt_text="Classify {domain}")
    sqlite_session.add(prompt)
    sqlite_session.commit()

    with pytest.raises(HTTPException) as exc:
        create_runs(
            payload=RunCreateRequest(
                campaign_id=campaign_a.id,
                prompt_id=prompt.id,
                scope="selected",
                company_ids=[company_a.id, company_b.id],
            ),
            session=sqlite_session,
        )
    assert exc.value.status_code == 422
