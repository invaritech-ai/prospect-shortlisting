from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.base import UTCReadModel


class ContactFetchResult(BaseModel):
    requested_count: int
    queued_count: int
    already_fetching_count: int
    queued_job_ids: list[UUID]
    reused_count: int = 0
    stale_reused_count: int = 0
    batch_id: UUID | None = None
    idempotency_key: str | None = None
    idempotency_replayed: bool = False


class TitleMatchRuleRead(UTCReadModel):
    id: UUID
    campaign_id: UUID | None = None
    rule_type: str
    match_type: str
    keywords: str
    created_at: datetime


class TitleMatchRuleCreate(BaseModel):
    campaign_id: UUID
    rule_type: str = Field(pattern="^(include|exclude)$")
    keywords: str = Field(min_length=1, max_length=255)
    match_type: str = Field(default="keyword", pattern="^(keyword|regex|seniority)$")


class TitleRuleSeedResult(BaseModel):
    inserted: int
    message: str


class BulkContactFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: UUID
    company_ids: list[UUID] = Field(min_length=1)
    force_refresh: bool = False


class RematchResult(BaseModel):
    updated: int
    fetch_jobs_queued: int
    message: str


class TitleTestRequest(BaseModel):
    campaign_id: UUID
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


class ContactCompanySummary(UTCReadModel):
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


class ContactVerifyRequest(BaseModel):
    campaign_id: UUID
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


class ContactRead(UTCReadModel):
    id: UUID
    company_id: UUID
    contact_fetch_job_id: UUID | None = None
    domain: str
    provider: str
    provider_person_id: str
    first_name: str
    last_name: str
    title: str | None
    title_match: bool
    linkedin_url: str | None
    source_url: str | None
    provider_has_email: bool | None
    is_active: bool
    backfilled: bool
    freshness_status: Literal["fresh", "stale"]
    group_key: str
    discovered_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    total: int
    has_more: bool
    limit: int
    offset: int
    items: list[ContactRead]
    letter_counts: dict[str, int] | None = None


class ContactCountsResponse(BaseModel):
    total: int
    matched: int
    stale: int
    fresh: int
    already_revealed: int


class ContactIdsResult(BaseModel):
    ids: list[UUID]
    total: int


class ContactRevealRequest(BaseModel):
    campaign_id: UUID
    discovered_contact_ids: list[UUID] | None = None
    company_ids: list[UUID] | None = None


class ContactRevealResult(BaseModel):
    batch_id: UUID | None = None
    selected_count: int
    queued_count: int
    already_revealing_count: int
    skipped_revealed_count: int
    message: str
    idempotency_key: str | None = None
    idempotency_replayed: bool = False


MatchGapFilter = Literal["all", "contacts_no_match", "matched_no_email", "ready_candidates"]


class ContactRuntimeControlRead(UTCReadModel):
    id: UUID
    auto_enqueue_enabled: bool
    auto_enqueue_paused: bool
    auto_enqueue_max_batch_size: int
    auto_enqueue_max_active_per_run: int
    dispatcher_batch_size: int
    reveal_enabled: bool
    reveal_paused: bool
    reveal_dispatcher_batch_size: int
    created_at: datetime
    updated_at: datetime


class ContactRuntimeControlUpdate(BaseModel):
    auto_enqueue_enabled: bool | None = None
    auto_enqueue_paused: bool | None = None
    auto_enqueue_max_batch_size: int | None = Field(default=None, ge=1)
    auto_enqueue_max_active_per_run: int | None = Field(default=None, ge=1)
    dispatcher_batch_size: int | None = Field(default=None, ge=1)
    reveal_enabled: bool | None = None
    reveal_paused: bool | None = None
    reveal_dispatcher_batch_size: int | None = Field(default=None, ge=1)


class ContactBatchSummary(UTCReadModel):
    batch_id: UUID
    trigger_source: str
    requested_provider_mode: str
    auto_enqueued: bool
    state: str
    requested_count: int
    queued_count: int
    already_fetching_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    updated_at: datetime


class ContactProviderBacklogItem(BaseModel):
    provider: str
    queued: int = 0
    running: int = 0
    deferred: int = 0
    succeeded: int = 0
    failed: int = 0
    dead: int = 0
    rate_limited: int = 0
    retryable: int = 0


class ContactBacklogSummary(BaseModel):
    job_counts: dict[str, int]
    attempt_counts: dict[str, int]
    provider_attempt_counts: list[ContactProviderBacklogItem]
    recent_batches: list[ContactBatchSummary]


class ContactRetryFailedRequest(BaseModel):
    campaign_id: UUID
    company_ids: list[UUID] | None = None
    provider_mode: Literal["snov", "apollo", "both"] = "both"


class ContactReplayDeferredRequest(BaseModel):
    batch_id: UUID | None = None
    provider: Literal["snov", "apollo", "both"] = "both"
    limit: int = Field(default=100, ge=1, le=1000)


class ContactReplayDeferredResult(BaseModel):
    replayed_attempt_count: int
    scheduled_job_count: int
