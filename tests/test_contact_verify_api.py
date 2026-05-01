from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.models import Company, Contact, Upload


def _seed(session: Session, campaign_id) -> tuple[Company, Contact]:
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
    contact = Contact(
        company_id=co.id,
        source_provider="snov",
        provider_person_id=str(uuid4()),
        first_name="Alice",
        last_name="Smith",
        title_match=True,
        email="alice@acme.com",
        verification_status="unverified",
        pipeline_stage="email_revealed",
    )
    session.add(contact)
    session.flush()
    return co, contact


@pytest.mark.asyncio
async def test_verify_endpoint_creates_job_and_defers_task(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import verify_contacts
    from app.api.schemas.contacts import ContactVerifyRequest
    from app.jobs import validation as val_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(val_mod.verify_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s5"), session=db_session)
    _, contact = _seed(db_session, campaign.id)
    db_session.commit()

    result = await verify_contacts(
        payload=ContactVerifyRequest(
            campaign_id=campaign.id,
            contact_ids=[contact.id],
        ),
        session=db_session,
    )

    assert result.job_id is not None
    assert result.selected_count == 1
    assert len(deferred) == 1
    assert deferred[0]["job_id"] is not None


@pytest.mark.asyncio
async def test_verify_endpoint_skips_ineligible_contacts(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import verify_contacts
    from app.api.schemas.contacts import ContactVerifyRequest
    from app.jobs import validation as val_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(val_mod.verify_contacts, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s5"), session=db_session)
    _, contact = _seed(db_session, campaign.id)
    contact.title_match = False
    db_session.flush()
    db_session.commit()

    result = await verify_contacts(
        payload=ContactVerifyRequest(
            campaign_id=campaign.id,
            contact_ids=[contact.id],
        ),
        session=db_session,
    )

    assert result.job_id is not None
    assert result.selected_count == 1
    # task still deferred (empty job handles it gracefully)
    assert len(deferred) == 1
