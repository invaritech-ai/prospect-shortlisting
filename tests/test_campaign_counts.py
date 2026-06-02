from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes.campaigns import create_campaign, list_campaigns
from app.api.schemas.campaign import CampaignCreate
from app.models import UploadedDomain


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_campaign_possible_count_accepts_lowercase_ai_decision_status(db_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Lowercase Possible"), session=db_session)
    db_session.add_all(
        [
            UploadedDomain(
                campaign_id=campaign.id,
                raw_url="https://possible.example",
                normalized_url="https://possible.example",
                domain="possible.example",
                dedupe_key="possible.example",
                decision_status="possible",
            ),
            UploadedDomain(
                campaign_id=campaign.id,
                raw_url="https://crap.example",
                normalized_url="https://crap.example",
                domain="crap.example",
                dedupe_key="crap.example",
                decision_status="crap",
            ),
        ]
    )
    db_session.commit()

    listed = list_campaigns(session=db_session, limit=200, offset=0)

    row = next(item for item in listed.items if item.id == campaign.id)
    assert row.classified_count == 2
    assert row.possible_count == 1
