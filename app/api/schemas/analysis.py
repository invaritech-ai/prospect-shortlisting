from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

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
