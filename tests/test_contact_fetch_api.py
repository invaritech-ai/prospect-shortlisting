from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.models import Company, ContactFetchJob, Upload
from app.models.pipeline import ContactFetchJobState


# ── helpers ───────────────────────────────────────────────────────────────────

def _seed(session: Session, campaign_id) -> Company:
    from app.models.pipeline import CompanyPipelineStage
    u = Upload(
        campaign_id=campaign_id,
        filename="f.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    session.add(u)
    session.flush()
    co = Company(
        upload_id=u.id,
        raw_url="https://acme.com",
        normalized_url="https://acme.com",
        domain="acme.com",
        pipeline_stage=CompanyPipelineStage.SCRAPED,
    )
    session.add(co)
    session.flush()
    return co


# ── Task 3: enqueue API ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_contacts_for_company_creates_job(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import fetch_contacts_for_company
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    db_session.commit()

    result = await fetch_contacts_for_company(
        company_id=company.id,
        campaign_id=campaign.id,
        force_refresh=False,
        session=db_session,
    )

    assert result.queued_count == 1
    assert result.already_fetching_count == 0
    assert len(deferred) == 1


@pytest.mark.asyncio
async def test_fetch_contacts_selected_queues_eligible_companies(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import fetch_contacts_selected
    from app.api.schemas.contacts import BulkContactFetchRequest
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    db_session.commit()

    result = await fetch_contacts_selected(
        payload=BulkContactFetchRequest(campaign_id=campaign.id, company_ids=[company.id]),
        session=db_session,
    )

    assert result.queued_count == 1
    assert len(deferred) == 1


# ── Task 5: GET /contacts/companies ──────────────────────────────────────────

def test_list_contacts_companies_groups_by_company(db_session: Session) -> None:
    from app.api.routes.contacts import list_contacts_companies
    from app.models import Contact

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    db_session.add(Contact(company_id=company.id, source_provider="snov", provider_person_id="s1", first_name="A", last_name="B", title_match=True))
    db_session.add(Contact(company_id=company.id, source_provider="apollo", provider_person_id="a1", first_name="C", last_name="D"))
    db_session.commit()

    result = list_contacts_companies(
        campaign_id=campaign.id,
        search=None,
        title_match=None,
        match_gap_filter="all",
        limit=50,
        offset=0,
        session=db_session,
    )

    assert result.total == 1
    assert result.items[0].company_id == company.id
    assert result.items[0].total_count == 2
    assert result.items[0].title_matched_count == 1


# ── Task 6: GET /contacts/ids ────────────────────────────────────────────────

def test_list_contact_ids_returns_matching_ids(db_session: Session) -> None:
    from app.api.routes.contacts import list_contact_ids
    from app.models import Contact

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    c1 = Contact(company_id=company.id, source_provider="snov", provider_person_id="s1", first_name="A", last_name="B", title_match=True)
    c2 = Contact(company_id=company.id, source_provider="apollo", provider_person_id="a1", first_name="C", last_name="D", title_match=False)
    db_session.add(c1)
    db_session.add(c2)
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    result = list_contact_ids(
        campaign_id=campaign.id,
        title_match=True,
        search=None,
        stale_days=None,
        letters=None,
        session=db_session,
    )

    assert result.total == 1
    assert c1.id in result.ids
    assert c2.id not in result.ids


# ── Task 5+: GET /companies/{id}/contacts ─────────────────────────────────────

def test_list_company_contacts_returns_contacts(db_session: Session) -> None:
    from app.api.routes.companies import list_company_contacts
    from app.models import Contact

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    db_session.add(Contact(
        company_id=company.id, source_provider="snov", provider_person_id="snov-1",
        first_name="Alice", last_name="Smith",
    ))
    db_session.commit()

    result = list_company_contacts(
        company_id=company.id,
        campaign_id=campaign.id,
        limit=50,
        offset=0,
        session=db_session,
    )

    assert result.total == 1
    assert result.items[0].first_name == "Alice"


# ── Task 3 (existing) ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_contacts_rejects_out_of_scope_company(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest as pt
    from fastapi import HTTPException
    from app.api.routes.companies import fetch_contacts_for_company
    from app.jobs import contact_fetch as cf_mod

    async def fake_defer(**kwargs):
        pass

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    other = create_campaign(payload=CampaignCreate(name="other"), session=db_session)
    company = _seed(db_session, other.id)
    db_session.commit()

    with pt.raises(HTTPException) as exc_info:
        await fetch_contacts_for_company(
            company_id=company.id,
            campaign_id=campaign.id,
            force_refresh=False,
            session=db_session,
        )
    assert exc_info.value.status_code == 400


# ── Gap 1: eligibility gate ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_contacts_selected_skips_uploaded_companies(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import fetch_contacts_selected
    from app.api.schemas.contacts import BulkContactFetchRequest
    from app.jobs import contact_fetch as cf_mod
    from app.models.pipeline import CompanyPipelineStage

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    scraped = _seed(db_session, campaign.id)          # SCRAPED via _seed default
    uploaded = _seed(db_session, campaign.id)
    uploaded.domain = "uploaded.com"
    uploaded.pipeline_stage = CompanyPipelineStage.UPLOADED
    db_session.flush()
    db_session.commit()

    result = await fetch_contacts_selected(
        payload=BulkContactFetchRequest(
            campaign_id=campaign.id,
            company_ids=[uploaded.id, scraped.id],
        ),
        session=db_session,
    )

    # Only scraped company queued; uploaded one skipped
    assert result.queued_count == 1
    assert result.requested_count == 2
    assert len(deferred) == 1


@pytest.mark.asyncio
async def test_fetch_contacts_for_company_rejects_uploaded(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest as pt
    from fastapi import HTTPException
    from app.api.routes.companies import fetch_contacts_for_company
    from app.jobs import contact_fetch as cf_mod

    async def fake_defer(**kwargs):
        pass

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    from app.models.pipeline import CompanyPipelineStage
    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    company.pipeline_stage = CompanyPipelineStage.UPLOADED
    db_session.flush()
    db_session.commit()

    with pt.raises(HTTPException) as exc_info:
        await fetch_contacts_for_company(
            company_id=company.id,
            campaign_id=campaign.id,
            force_refresh=False,
            session=db_session,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_stuck_contact_fetch_jobs_requeues_running_without_lock(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import reset_stuck_contact_fetch_jobs
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    job = ContactFetchJob(
        company_id=company.id,
        provider="snov",
        state=ContactFetchJobState.RUNNING,
        terminal_state=False,
        lock_token="stale-lock",
        lock_expires_at=None,
    )
    db_session.add(job)
    db_session.commit()

    result = await reset_stuck_contact_fetch_jobs(session=db_session)

    db_session.refresh(job)
    assert result.reset_count == 1
    assert job.state == ContactFetchJobState.QUEUED
    assert job.terminal_state is False
    assert job.lock_token is None
    assert len(deferred) == 1
    assert deferred[0]["contact_fetch_job_id"] == str(job.id)


@pytest.mark.asyncio
async def test_reset_stuck_contact_fetch_jobs_ignores_terminal_jobs(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import reset_stuck_contact_fetch_jobs
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=db_session)
    company = _seed(db_session, campaign.id)
    job = ContactFetchJob(
        company_id=company.id,
        provider="snov",
        state=ContactFetchJobState.FAILED,
        terminal_state=True,
    )
    db_session.add(job)
    db_session.commit()

    result = await reset_stuck_contact_fetch_jobs(session=db_session)

    db_session.refresh(job)
    assert result.reset_count == 0
    assert job.state == ContactFetchJobState.FAILED
    assert len(deferred) == 0
