from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import utc_datetime_field, utcnow


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str = Field(max_length=255, index=True)
    description: str | None = Field(default=None, max_length=2000)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    updated_at: datetime = utc_datetime_field(default_factory=utcnow)


class Upload(SQLModel, table=True):
    __tablename__ = "uploads"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    filename: str = Field(max_length=1024)
    checksum: str = Field(max_length=128, index=True)
    row_count: int = Field(default=0, ge=0)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)


class UploadedDomain(SQLModel, table=True):
    """
    A deduplicated domain belonging to a campaign.
    upload_id is nullable because after deduplication the domain belongs to
    the campaign directly, not only through the upload.

    Status columns track the latest completed stage outcome for this domain
    and are updated by each stage's service after writing its result row.
    """

    __tablename__ = "uploaded_domains"
    __table_args__ = (
        UniqueConstraint("campaign_id", "dedupe_key", name="uq_uploaded_domains_campaign_dedupe"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    upload_id: UUID | None = Field(default=None, foreign_key="uploads.id", index=True)
    raw_url: str = Field(sa_column=Column(Text, nullable=False))
    normalized_url: str = Field(max_length=2048)
    domain: str = Field(max_length=255, index=True)
    dedupe_key: str = Field(max_length=255, index=True)

    # Current stage status — null = stage not yet attempted
    scrape_status: str | None = Field(default=None, max_length=32, index=True)
    decision_status: str | None = Field(default=None, max_length=32, index=True)
    fetch_status: str | None = Field(default=None, max_length=32, index=True)
    verify_status: str | None = Field(default=None, max_length=32, index=True)

    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
