from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.base import UTCReadModel


EmailFetchMode = Literal["fetch", "refetch"]


class EmailFetchPreviewRequest(BaseModel):
    campaign_id: UUID
    domain_ids: list[UUID] = Field(min_length=1, max_length=200)
    mode: EmailFetchMode = "fetch"


class EmailFetchBatchCreate(BaseModel):
    campaign_id: UUID
    domain_ids: list[UUID] = Field(min_length=1, max_length=200)
    mode: EmailFetchMode = "fetch"


class EmailFetchCriteriaSaveRequest(BaseModel):
    campaign_id: UUID
    include_titles: list[str] = Field(default_factory=list)
    exclude_titles: list[str] = Field(default_factory=list)
    target_contacts_per_company: int = Field(default=3, ge=1, le=3)


class EmailFetchCriteriaRead(UTCReadModel):
    id: UUID | None = None
    campaign_id: UUID
    include_titles: list[str]
    exclude_titles: list[str]
    target_contacts_per_company: int
    criteria_hash: str
    is_active: bool
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EmailFetchPreviewCandidate(BaseModel):
    domain_id: UUID
    domain: str
    provider: str
    provider_person_id: str
    first_name: str
    last_name: str
    title: str
    linkedin_url: str | None = None


class EmailFetchPreviewDomain(BaseModel):
    domain_id: UUID
    domain: str
    matched_candidate_count: int
    estimated_apollo_reveals: int
    estimated_snov_fallback: int
    candidates: list[EmailFetchPreviewCandidate]
    warnings: list[str] = Field(default_factory=list)


class EmailFetchPreviewRead(BaseModel):
    campaign_id: UUID
    mode: EmailFetchMode = "fetch"
    selected_domain_count: int
    target_contacts_per_company: int
    estimated_apollo_reveals: int
    estimated_snov_fallback_min: int
    credit_plan: dict[str, Any]
    criteria_hash: str
    criteria_snapshot: dict[str, Any]
    domains: list[EmailFetchPreviewDomain]
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EmailFetchBatchRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    state: str
    selected_domain_count: int
    queued_count: int
    success_count: int
    failed_count: int
    criteria_hash: str | None
    criteria_snapshot: dict[str, Any] | None
    provider_order: list[str]
    result_summary: dict[str, Any] | None
    created_at: datetime
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EmailFetchCompanyCounts(BaseModel):
    all: int = 0
    pending: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0
    no_match: int = 0
    contacts_found: int = 0
    emails_found: int = 0
    fetched_people_found: int = 0

    model_config = ConfigDict(from_attributes=True)


class EmailFetchCompanyRow(UTCReadModel):
    domain_id: UUID
    campaign_id: UUID
    domain: str
    normalized_url: str
    fetch_status: str | None
    status: str
    contacts_found: int
    emails_found: int
    fetched_people_found: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailFetchCompanyList(BaseModel):
    total: int
    limit: int
    offset: int
    counts: EmailFetchCompanyCounts
    items: list[EmailFetchCompanyRow]

    model_config = ConfigDict(from_attributes=True)


class EmailFetchCompanyIds(BaseModel):
    ids: list[UUID]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(from_attributes=True)
