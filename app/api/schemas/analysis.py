from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from pydantic import Field

from app.api.schemas.base import UTCReadModel


class AiReviewDomainRow(UTCReadModel):
    domain_id: UUID
    campaign_id: UUID
    domain: str
    raw_url: str
    normalized_url: str
    classification_result_id: UUID | None
    classification_state: str | None
    predicted_label: str | None
    confidence: Decimal | None
    reasoning_json: dict[str, Any] | None
    evidence_json: dict[str, Any] | None
    manual_label: str | None
    manual_thumbs: str | None
    manual_comment: str | None
    manually_reviewed_at: datetime | None
    effective_label: str | None
    effective_confidence: Decimal | None
    pages_reviewed: int = 0
    activity_at: datetime


class AiReviewDomainAnalysis(AiReviewDomainRow):
    pass


class AiReviewDomainList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AiReviewDomainRow]


class AiReviewLabelCounts(BaseModel):
    all: int
    unclassified: int
    possible: int
    unknown: int
    crap: int


class AiReviewJobCreate(BaseModel):
    campaign_id: UUID
    domain_ids: list[UUID] = Field(default_factory=list)
    label: str | None = None
    letter: str | None = None
    search: str | None = None


class AiReviewJobRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    state: str
    selected_domain_count: int
    queued_count: int
    success_count: int
    failed_count: int
    created_at: datetime
    finished_at: datetime | None = None


class AiReviewJobStatusRead(UTCReadModel):
    batch_id: UUID
    campaign_id: UUID
    state: str
    selected: int
    queued: int
    running: int
    succeeded: int
    failed: int
    terminal: int
    queue_todo: int
    queue_doing: int
    queue_succeeded: int
    queue_failed: int
    queue_cancelled: int
    queue_aborting: int
    queue_aborted: int
    created_at: datetime
    finished_at: datetime | None = None
