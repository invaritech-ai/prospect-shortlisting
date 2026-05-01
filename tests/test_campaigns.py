from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlmodel import Session

from app.api.routes.campaigns import (
    assign_uploads_to_campaign,
    create_campaign,
    get_campaign_costs,
    list_campaigns,
)
from app.api.schemas.campaign import CampaignAssignUploadsRequest, CampaignCreate
from app.models import AiUsageEvent, Upload
from app.services.upload_service import UploadService


def test_create_and_list_campaign(db_session: Session) -> None:
    before = list_campaigns(session=db_session, limit=200, offset=0)
    created = create_campaign(
        payload=CampaignCreate(name="Q2 Outreach", description="Primary outbound push"),
        session=db_session,
    )
    assert created.name == "Q2 Outreach"

    listed = list_campaigns(session=db_session, limit=200, offset=0)
    assert listed.total == before.total + 1
    assert any(item.id == created.id for item in listed.items)


def test_assign_existing_uploads_to_campaign(db_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Assign Test"), session=db_session)
    upload = Upload(
        filename="domains.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    db_session.add(upload)
    db_session.commit()
    db_session.refresh(upload)

    result = assign_uploads_to_campaign(
        campaign_id=campaign.id,
        payload=CampaignAssignUploadsRequest(upload_ids=[upload.id]),
        session=db_session,
    )
    assert result.upload_count == 1


def test_upload_service_respects_campaign_id(db_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Upload Scope"), session=db_session)
    service = UploadService()
    payload = b"website\nhttps://example.com\n"
    upload, issues, reused = service.create_upload_from_file(
        session=db_session,
        filename="test.csv",
        raw_bytes=payload,
        campaign_id=campaign.id,
    )
    assert issues == []
    assert reused == 0
    assert upload.campaign_id == campaign.id


def test_campaign_costs_summarize_usage_events(db_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Campaign Costs"), session=db_session)
    other = create_campaign(payload=CampaignCreate(name="Other Campaign Costs"), session=db_session)
    db_session.add(
        AiUsageEvent(
            campaign_id=campaign.id,
            stage="analysis",
            billed_cost_usd=Decimal("0.125000"),
            input_tokens=100,
            output_tokens=25,
        )
    )
    db_session.add(
        AiUsageEvent(
            campaign_id=campaign.id,
            stage="contacts",
            billed_cost_usd=Decimal("0.025000"),
            input_tokens=10,
            output_tokens=5,
        )
    )
    db_session.add(AiUsageEvent(campaign_id=other.id, stage="analysis", billed_cost_usd=Decimal("9.000000")))
    db_session.commit()

    costs = get_campaign_costs(campaign_id=campaign.id, session=db_session)

    assert costs.campaign_id == campaign.id
    assert costs.pipeline_run_id is None
    assert costs.total_cost_usd == Decimal("0.150000")
    assert costs.event_count == 2
    assert costs.input_tokens == 110
    assert costs.output_tokens == 30
    assert costs.by_stage["analysis"].cost_usd == Decimal("0.125000")
    assert costs.by_stage["contacts"].cost_usd == Decimal("0.025000")
