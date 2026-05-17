from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON, Numeric, Text
from sqlmodel import Field, SQLModel

from app.models.base import utc_datetime_field, utcnow


class DecisionSettings(SQLModel, table=True):
    """
    Append-only AI classification prompt + model config.
    campaign_id=None means global default.
    """

    __tablename__ = "decision_settings"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    name: str = Field(max_length=255)
    instruction_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    model: str = Field(default="", max_length=128)
    settings_hash: str = Field(max_length=64, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)


class ClassificationBatch(SQLModel, table=True):
    """One operator action to classify a set of scraped domains."""

    __tablename__ = "classification_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    decision_settings_id: UUID | None = Field(
        default=None, foreign_key="decision_settings.id", index=True
    )
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


class ClassificationResult(SQLModel, table=True):
    """
    Per-domain AI classification result for one batch.
    AI result columns are never overwritten after write.
    Manual feedback stored in separate columns alongside the AI result.
    """

    __tablename__ = "classification_results"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    domain_id: UUID = Field(foreign_key="uploaded_domains.id", index=True)
    scrape_result_id: UUID | None = Field(default=None, foreign_key="scrape_results.id", index=True)
    classification_batch_id: UUID | None = Field(
        default=None, foreign_key="classification_batches.id", index=True
    )
    state: str = Field(default="queued", max_length=32, index=True)

    # AI result — never mutated after write
    predicted_label: str | None = Field(default=None, max_length=32, index=True)  # possible/crap/unknown
    confidence: Decimal | None = Field(default=None, sa_column=Column(Numeric(5, 4), nullable=True))
    reasoning_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    evidence_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    input_hash: str | None = Field(default=None, max_length=64, index=True)
    settings_hash: str | None = Field(default=None, max_length=64)

    # Manual feedback — stored alongside AI result, never overwrites it
    manual_label: str | None = Field(default=None, max_length=32)
    manual_thumbs: str | None = Field(default=None, max_length=8)   # up / down
    manual_comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    manually_reviewed_at: datetime | None = utc_datetime_field(default=None, nullable=True)

    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
