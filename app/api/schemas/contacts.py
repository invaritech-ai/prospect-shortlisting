from __future__ import annotations

from datetime import datetime
from typing import Literal
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
    idempotency_key: str | None = None
    idempotency_replayed: bool = False


class TitleMatchRuleRead(BaseModel):
    id: UUID
    rule_type: str
    match_type: str
    keywords: str
    created_at: datetime


class TitleMatchRuleCreate(BaseModel):
    rule_type: str = Field(pattern="^(include|exclude)$")
    keywords: str = Field(min_length=1, max_length=255)
    match_type: str = Field(default="keyword", pattern="^(keyword|regex|seniority)$")


class TitleRuleSeedResult(BaseModel):
    inserted: int
    message: str


class BulkContactFetchRequest(BaseModel):
    company_ids: list[UUID] = Field(min_length=1)
    source: Literal["snov", "apollo", "both"] = "snov"


class RematchResult(BaseModel):
    updated: int
    fetch_jobs_queued: int
    message: str


class TitleTestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)


class TitleTestResult(BaseModel):
    matched: bool
    matching_rules: list[str]   # original keyword strings that matched, e.g. ["marketing, director"]
    excluded_by: list[str]      # exclude keywords that fired, e.g. ["assistant"]
    normalized_title: str


class TitleRuleStatItem(BaseModel):
    rule_id: UUID
    rule_type: str
    keywords: str
    contact_match_count: int


class TitleRuleStatsResponse(BaseModel):
    rules: list[TitleRuleStatItem]
    total_contacts: int
    total_matched: int


class ContactCompanySummary(BaseModel):
    company_id: UUID
    domain: str
    total_count: int
    title_matched_count: int
    unmatched_count: int = 0
    matched_no_email_count: int = 0
    email_count: int
    fetched_count: int
    verified_count: int
    campaign_ready_count: int
    eligible_verify_count: int
    last_contact_attempted_at: datetime | None = None


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
    idempotency_key: str | None = None
    idempotency_replayed: bool = False


MatchGapFilter = Literal["all", "contacts_no_match", "matched_no_email", "ready_candidates"]
