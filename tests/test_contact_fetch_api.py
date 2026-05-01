from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.models import Company, Upload


# ── helpers ───────────────────────────────────────────────────────────────────

def _seed(session: Session, campaign_id) -> Company:
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
    )
    session.add(co)
    session.flush()
    return co


# ── Task 3: enqueue API ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_contacts_for_company_creates_job(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import fetch_contacts_for_company
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    company = _seed(sqlite_session, campaign.id)
    sqlite_session.commit()

    result = await fetch_contacts_for_company(
        company_id=company.id,
        campaign_id=campaign.id,
        force_refresh=False,
        session=sqlite_session,
    )

    assert result.queued_count == 1
    assert result.already_fetching_count == 0
    assert len(deferred) == 1


@pytest.mark.asyncio
async def test_fetch_contacts_selected_queues_eligible_companies(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.companies import fetch_contacts_selected
    from app.api.schemas.contacts import BulkContactFetchRequest
    from app.jobs import contact_fetch as cf_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    company = _seed(sqlite_session, campaign.id)
    sqlite_session.commit()

    result = await fetch_contacts_selected(
        payload=BulkContactFetchRequest(campaign_id=campaign.id, company_ids=[company.id]),
        session=sqlite_session,
    )

    assert result.queued_count == 1
    assert len(deferred) == 1


@pytest.mark.asyncio
async def test_fetch_contacts_rejects_out_of_scope_company(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest as pt
    from fastapi import HTTPException
    from app.api.routes.companies import fetch_contacts_for_company
    from app.jobs import contact_fetch as cf_mod

    async def fake_defer(**kwargs):
        pass

    monkeypatch.setattr(cf_mod.fetch_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s3"), session=sqlite_session)
    other = create_campaign(payload=CampaignCreate(name="other"), session=sqlite_session)
    company = _seed(sqlite_session, other.id)
    sqlite_session.commit()

    with pt.raises(HTTPException) as exc_info:
        await fetch_contacts_for_company(
            company_id=company.id,
            campaign_id=campaign.id,
            force_refresh=False,
            session=sqlite_session,
        )
    assert exc_info.value.status_code == 400
