from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session

from app.api.routes.campaigns import (
    assign_uploads_to_campaign,
    create_campaign,
    list_campaigns,
)
from app.api.schemas.campaign import CampaignAssignUploadsRequest, CampaignCreate
from app.models import Upload
from app.services.upload_service import UploadService


def test_create_and_list_campaign(sqlite_session: Session) -> None:
    before = list_campaigns(session=sqlite_session, limit=200, offset=0)
    created = create_campaign(
        payload=CampaignCreate(name="Q2 Outreach", description="Primary outbound push"),
        session=sqlite_session,
    )
    assert created.name == "Q2 Outreach"

    listed = list_campaigns(session=sqlite_session, limit=200, offset=0)
    assert listed.total == before.total + 1
    assert any(item.id == created.id for item in listed.items)


def test_assign_existing_uploads_to_campaign(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Assign Test"), session=sqlite_session)
    upload = Upload(
        filename="domains.csv",
        checksum=str(uuid4()),
        row_count=1,
        valid_count=1,
        invalid_count=0,
    )
    sqlite_session.add(upload)
    sqlite_session.commit()
    sqlite_session.refresh(upload)

    result = assign_uploads_to_campaign(
        campaign_id=campaign.id,
        payload=CampaignAssignUploadsRequest(upload_ids=[upload.id]),
        session=sqlite_session,
    )
    assert result.upload_count == 1


def test_upload_service_respects_campaign_id(sqlite_session: Session) -> None:
    campaign = create_campaign(payload=CampaignCreate(name="Upload Scope"), session=sqlite_session)
    service = UploadService()
    payload = b"website\nhttps://example.com\n"
    upload, issues, reused = service.create_upload_from_file(
        session=sqlite_session,
        filename="test.csv",
        raw_bytes=payload,
        campaign_id=campaign.id,
    )
    assert issues == []
    assert reused == 0
    assert upload.campaign_id == campaign.id
