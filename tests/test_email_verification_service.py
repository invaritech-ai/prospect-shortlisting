from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Campaign, Contact, EmailVerificationCache, UploadedDomain
from app.models.base import utcnow
from app.services.email_verification_service import (
    is_campaign_ready_contact,
    normalize_email,
)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _campaign(session: Session) -> Campaign:
    campaign = Campaign(name="S4 Campaign")
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def _domain(session: Session, campaign_id: UUID) -> UploadedDomain:
    domain = UploadedDomain(
        campaign_id=campaign_id,
        raw_url="https://example.com",
        normalized_url="https://example.com",
        domain="example.com",
        dedupe_key="example.com",
    )
    session.add(domain)
    session.commit()
    session.refresh(domain)
    return domain


def test_email_verification_cache_persists_normalized_email(db_session: Session) -> None:
    cache = EmailVerificationCache(
        normalized_email=normalize_email("  PERSON@Example.COM  "),
        status="valid",
        sub_status=None,
        raw_json={"address": "PERSON@Example.COM", "status": "valid"},
    )

    db_session.add(cache)
    db_session.commit()

    saved = db_session.exec(select(EmailVerificationCache)).one()
    assert saved.provider == "zerobounce"
    assert saved.normalized_email == "person@example.com"
    assert saved.status == "valid"
    assert saved.raw_json == {"address": "PERSON@Example.COM", "status": "valid"}


def test_contact_ready_rule_uses_current_email_snapshot(db_session: Session) -> None:
    now = utcnow()
    campaign = _campaign(db_session)
    domain = _domain(db_session, campaign.id)
    contact = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        selected_email="current@example.com",
        verification_applied=True,
        verification_status="VALID",
        verified_email_snapshot="old@example.com",
        verified_at=now - timedelta(days=1),
    )

    assert is_campaign_ready_contact(contact, now=now) is False

    contact.verified_email_snapshot = " CURRENT@example.com "
    assert is_campaign_ready_contact(contact, now=now) is True

    contact.verified_at = now - timedelta(days=31)
    assert is_campaign_ready_contact(contact, now=now) is False
