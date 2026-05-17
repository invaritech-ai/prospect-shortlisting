from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel

from app.models.base import utc_datetime_field, utcnow


class ScrapeSettings(SQLModel, table=True):
    """
    Append-only scrape config. Create a new row when settings change; never mutate.
    campaign_id=None means global default.
    """

    __tablename__ = "scrape_settings"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    name: str = Field(max_length=255)
    instruction_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    structured_rules_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    settings_hash: str = Field(max_length=64, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)


class ScrapeBatch(SQLModel, table=True):
    """One operator action to scrape a set of domains in a campaign."""

    __tablename__ = "scrape_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    scrape_settings_id: UUID | None = Field(default=None, foreign_key="scrape_settings.id", index=True)
    settings_snapshot_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    settings_hash: str | None = Field(default=None, max_length=64)
    state: str = Field(default="queued", max_length=32, index=True)
    selected_domain_count: int = Field(default=0, ge=0)
    queued_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    finished_at: datetime | None = utc_datetime_field(default=None, nullable=True)


class ScrapeResult(SQLModel, table=True):
    """Per-domain outcome for one scrape batch. Source input for S2 classification."""

    __tablename__ = "scrape_results"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    domain_id: UUID = Field(foreign_key="uploaded_domains.id", index=True)
    scrape_batch_id: UUID | None = Field(default=None, foreign_key="scrape_batches.id", index=True)
    state: str = Field(default="queued", max_length=32, index=True)
    pages_attempted_count: int = Field(default=0, ge=0)
    pages_success_count: int = Field(default=0, ge=0)
    markdown_pages_count: int = Field(default=0, ge=0)
    scraped_pages_json: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    error_code: str | None = Field(default=None, max_length=128)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    updated_at: datetime = utc_datetime_field(default_factory=utcnow)
