from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes.campaigns import create_campaign, list_campaigns
from app.api.schemas.campaign import CampaignCreate
from app.models import ClassificationResult, Contact, UploadedDomain
from app.models.base import utcnow


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _domain(campaign_id, domain: str, *, scrape_status: str | None = "succeeded", decision_status: str | None = None) -> UploadedDomain:
    return UploadedDomain(
        campaign_id=campaign_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        dedupe_key=domain,
        scrape_status=scrape_status,
        decision_status=decision_status,
    )


def test_campaign_ai_counts_use_effective_classification_scope(db_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Effective AI Counts"), session=db_session)
    possible = _domain(campaign.id, "possible.example", decision_status="crap")
    unknown = _domain(campaign.id, "unknown.example")
    crap = _domain(campaign.id, "crap.example")
    unclassified = _domain(campaign.id, "unclassified.example")
    legacy_status_only = _domain(campaign.id, "legacy.example", decision_status="crap")
    db_session.add_all([possible, unknown, crap, unclassified, legacy_status_only])
    db_session.commit()
    db_session.add_all(
        [
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=possible.id,
                state="succeeded",
                predicted_label="crap",
                manual_label="possible",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=unknown.id,
                state="succeeded",
                predicted_label="unknown",
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=crap.id,
                state="succeeded",
                predicted_label="crap",
            ),
        ]
    )
    db_session.commit()

    listed = list_campaigns(session=db_session, limit=200, offset=0)

    row = next(item for item in listed.items if item.id == campaign.id)
    assert row.scrape_count == 5
    assert row.classified_count == 2
    assert row.possible_count == 1


def test_campaign_valid_email_count_only_counts_fresh_current_valid_contacts(db_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Valid Email Count"), session=db_session)
    domain = UploadedDomain(
        campaign_id=campaign.id,
        raw_url="https://valid.example",
        normalized_url="https://valid.example",
        domain="valid.example",
        dedupe_key="valid.example",
    )
    db_session.add(domain)
    db_session.commit()
    db_session.refresh(domain)

    now = utcnow()
    valid = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Valid",
        last_name="Person",
        selected_email="Valid@Example.com",
        verified_email_snapshot="valid@example.com",
        verification_status="VALID",
        verification_applied=True,
        verified_at=now - timedelta(days=1),
    )
    stale = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Stale",
        last_name="Person",
        selected_email="stale@example.com",
        verified_email_snapshot="stale@example.com",
        verification_status="valid",
        verification_applied=True,
        verified_at=now - timedelta(days=31),
    )
    changed = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Changed",
        last_name="Person",
        selected_email="changed@example.com",
        verified_email_snapshot="old@example.com",
        verification_status="valid",
        verification_applied=True,
        verified_at=now,
    )
    undeliverable = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Bad",
        last_name="Person",
        selected_email="bad@example.com",
        verified_email_snapshot="bad@example.com",
        verification_status="invalid",
        verification_applied=True,
        verified_at=now,
    )
    db_session.add_all([valid, stale, changed, undeliverable])
    db_session.commit()

    listed = list_campaigns(session=db_session, limit=200, offset=0)

    row = next(item for item in listed.items if item.id == campaign.id)
    assert row.valid_email_count == 1
