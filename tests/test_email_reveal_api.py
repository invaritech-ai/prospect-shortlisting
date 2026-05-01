from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from app.api.routes.campaigns import create_campaign
from app.api.schemas.campaign import CampaignCreate
from app.models import Company, Contact, Upload


def _seed(session: Session, campaign_id) -> tuple[Company, Contact]:
    upload = Upload(
        campaign_id=campaign_id,
        filename="f.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    session.add(upload)
    session.flush()
    company = Company(
        upload_id=upload.id,
        raw_url="https://acme.com",
        normalized_url="https://acme.com",
        domain="acme.com",
    )
    session.add(company)
    session.flush()
    contact = Contact(
        company_id=company.id,
        source_provider="snov",
        provider_person_id="snov-1",
        first_name="Alice",
        last_name="Smith",
        title_match=True,
        email=None,
    )
    session.add(contact)
    session.flush()
    return company, contact


@pytest.mark.asyncio
async def test_reveal_endpoint_defers_tasks_for_eligible(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import reveal_contacts
    from app.api.schemas.contacts import ContactRevealRequest
    from app.jobs import email_reveal as er_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(er_mod.reveal_email, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s4"), session=db_session)
    _, contact = _seed(db_session, campaign.id)
    db_session.commit()

    result = await reveal_contacts(
        payload=ContactRevealRequest(
            campaign_id=campaign.id,
            discovered_contact_ids=[contact.id],
        ),
        session=db_session,
    )

    assert result.queued_count == 1
    assert result.skipped_revealed_count == 0
    assert len(deferred) == 1
    assert deferred[0]["contact_id"] == str(contact.id)


@pytest.mark.asyncio
async def test_reveal_endpoint_skips_no_title_match(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import reveal_contacts
    from app.api.schemas.contacts import ContactRevealRequest
    from app.jobs import email_reveal as er_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(er_mod.reveal_email, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s4"), session=db_session)
    _, contact = _seed(db_session, campaign.id)
    contact.title_match = False
    db_session.flush()
    db_session.commit()

    result = await reveal_contacts(
        payload=ContactRevealRequest(
            campaign_id=campaign.id,
            discovered_contact_ids=[contact.id],
        ),
        session=db_session,
    )

    assert result.queued_count == 0
    assert result.skipped_revealed_count == 1
    assert len(deferred) == 0


@pytest.mark.asyncio
async def test_reveal_endpoint_ignores_out_of_scope_contacts(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes.contacts import reveal_contacts
    from app.api.schemas.contacts import ContactRevealRequest
    from app.jobs import email_reveal as er_mod

    deferred: list[dict] = []

    async def fake_defer(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(er_mod.reveal_email, "defer_async", fake_defer)

    campaign = create_campaign(payload=CampaignCreate(name="s4"), session=db_session)
    other_campaign = create_campaign(payload=CampaignCreate(name="other"), session=db_session)
    _, contact = _seed(db_session, campaign.id)
    _, other_contact = _seed(db_session, other_campaign.id)
    db_session.commit()

    result = await reveal_contacts(
        payload=ContactRevealRequest(
            campaign_id=campaign.id,
            discovered_contact_ids=[contact.id, other_contact.id],
        ),
        session=db_session,
    )

    assert result.queued_count == 1
    assert result.skipped_revealed_count == 1
    assert len(deferred) == 1
    assert deferred[0]["contact_id"] == str(contact.id)
