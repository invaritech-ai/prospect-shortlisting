from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import utc_datetime_field, utcnow


class LlmRateLimit(SQLModel, table=True):
    """Global provider/purpose rate-limit bucket shared by all worker processes."""

    __tablename__ = "llm_rate_limits"
    __table_args__ = (
        UniqueConstraint("provider", "purpose", name="uq_llm_rate_limits_provider_purpose"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    provider: str = Field(max_length=64, index=True)
    purpose: str = Field(max_length=64, index=True)
    requests_per_minute: int = Field(default=12, ge=1)
    min_gap_ms: int = Field(default=5000, ge=0)
    window_started_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    requests_used: int = Field(default=0, ge=0)
    last_request_at: datetime | None = utc_datetime_field(default=None, nullable=True)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    updated_at: datetime = utc_datetime_field(default_factory=utcnow)
