from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProspectContactRead(BaseModel):
    id: UUID
    company_id: UUID
    contact_fetch_job_id: UUID
    domain: str
    source: str
    first_name: str
    last_name: str
    title: str | None
    title_match: bool
    linkedin_url: str | None
    email: str | None
    pipeline_stage: str
    provider_email_status: str | None
    verification_status: str
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


class RematchResult(BaseModel):
    updated: int
    fetch_jobs_queued: int
    message: str


class ContactCompanySummary(BaseModel):
    company_id: UUID
    domain: str
    total_count: int
    title_matched_count: int
    email_count: int
    fetched_count: int
    verified_count: int
    campaign_ready_count: int
    eligible_verify_count: int


class ContactCompanyListResponse(BaseModel):
    total: int
    has_more: bool
    limit: int
    offset: int
    items: list[ContactCompanySummary]


class ContactCountsResponse(BaseModel):
    total: int
    fetched: int
    verified: int
    campaign_ready: int
    eligible_verify: int


class ContactVerifyRequest(BaseModel):
    contact_ids: list[UUID] | None = None
    company_ids: list[UUID] | None = None
    title_match: bool | None = None
    verification_status: str | None = None
    search: str | None = None
    stage_filter: str | None = None


class ContactVerifyResult(BaseModel):
    job_id: UUID
    selected_count: int
    message: str
