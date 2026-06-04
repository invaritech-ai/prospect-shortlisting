from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.base import UTCReadModel


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CampaignRead(UTCReadModel):
    id: UUID
    name: str
    description: str | None = None
    upload_count: int = 0
    company_count: int = 0
    scrape_count: int = 0
    classified_count: int = 0
    possible_count: int = 0
    contact_count: int = 0
    created_at: datetime
    updated_at: datetime


class CampaignList(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool
    items: list[CampaignRead]


class CampaignAssignUploadsRequest(BaseModel):
    upload_ids: list[UUID] = Field(min_length=1)


class ScrapingStageCounts(BaseModel):
    badge: int = 0
    total: int = 0
    pending: int = 0
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    retryable_failed: int = 0
    is_live: bool = False


class AiReviewStageCounts(BaseModel):
    badge: int = 0
    all: int = 0
    unclassified: int = 0
    possible: int = 0
    unknown: int = 0
    crap: int = 0
    queued: int = 0
    running: int = 0
    is_live: bool = False


class ContactsStageCounts(BaseModel):
    badge: int = 0
    all: int = 0
    pending: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0
    no_match: int = 0
    contacts_found: int = 0
    emails_found: int = 0
    fetched_people_found: int = 0
    is_live: bool = False


class ValidationStageCounts(BaseModel):
    badge: int = 0
    total: int = 0
    pending: int = 0
    checking: int = 0
    running: int = 0
    stale: int = 0
    valid: int = 0
    undeliverable: int = 0
    catch_all: int = 0
    unknown: int = 0
    failed: int = 0
    invalid: int = 0
    is_live: bool = False


class CampaignStageCounts(BaseModel):
    campaign_id: UUID
    updated_at: datetime
    scraping: ScrapingStageCounts
    ai_review: AiReviewStageCounts
    contacts: ContactsStageCounts
    validation: ValidationStageCounts
