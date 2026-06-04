from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.base import UTCReadModel


EmailVerificationStatus = Literal[
    "pending",
    "checking",
    "stale",
    "valid",
    "undeliverable",
    "catch_all",
    "unknown",
    "failed",
]


class EmailVerificationCounts(BaseModel):
    all: int = 0
    pending: int = 0
    checking: int = 0
    stale: int = 0
    valid: int = 0
    undeliverable: int = 0
    catch_all: int = 0
    unknown: int = 0
    failed: int = 0

    model_config = ConfigDict(from_attributes=True)


class EmailVerificationContactRow(UTCReadModel):
    contact_id: UUID
    campaign_id: UUID
    domain_id: UUID
    domain: str
    first_name: str
    last_name: str
    title: str | None
    linkedin_url: str | None
    selected_email: str
    status: EmailVerificationStatus
    raw_status: str | None
    sub_status: str | None
    verified_at: datetime | None
    updated_at: datetime
    action_label: str | None

    model_config = ConfigDict(from_attributes=True)


class EmailVerificationContactList(BaseModel):
    total: int
    limit: int
    offset: int
    counts: EmailVerificationCounts
    items: list[EmailVerificationContactRow]


class EmailVerificationContactIds(BaseModel):
    ids: list[UUID]
    total: int
    limit: int
    offset: int


class EmailVerificationPreviewRequest(BaseModel):
    campaign_id: UUID
    contact_ids: list[UUID] = Field(min_length=1, max_length=200)


class EmailVerificationPreviewRead(BaseModel):
    campaign_id: UUID
    selected_count: int
    eligible_count: int
    cached_count: int
    paid_validation_count: int
    skipped_count: int
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
    max_batch_size: int = 200
    warnings: list[str] = Field(default_factory=list)
