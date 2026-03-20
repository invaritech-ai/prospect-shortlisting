from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProspectContactRead(BaseModel):
    id: UUID
    company_id: UUID
    contact_fetch_job_id: UUID
    source: str
    first_name: str
    last_name: str
    title: str | None
    title_match: bool
    linkedin_url: str | None
    email: str | None
    email_status: str
    snov_confidence: float | None
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    total: int
    has_more: bool
    limit: int
    offset: int
    items: list[ProspectContactRead]


class ContactFetchResult(BaseModel):
    requested_count: int
    queued_count: int
    already_fetching_count: int
    queued_job_ids: list[UUID]


class TitleMatchRuleRead(BaseModel):
    id: UUID
    rule_type: str
    keywords: str
    created_at: datetime


class TitleMatchRuleCreate(BaseModel):
    rule_type: str = Field(pattern="^(include|exclude)$")
    keywords: str = Field(min_length=2, max_length=255)


class TitleRuleSeedResult(BaseModel):
    inserted: int
    message: str
