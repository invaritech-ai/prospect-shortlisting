from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.base import UTCReadModel
from app.api.schemas.scrape import ScrapeRules


class UploadValidationError(BaseModel):
    row_number: int = Field(ge=1)
    raw_value: str
    error_code: str
    error_message: str


class UploadRead(UTCReadModel):
    id: UUID
    campaign_id: UUID | None = None
    filename: str
    checksum: str
    row_count: int
    valid_count: int
    invalid_count: int
    created_at: datetime


class UploadCreateResult(BaseModel):
    upload: UploadRead
    validation_errors: list[UploadValidationError]


class UploadDetail(BaseModel):
    upload: UploadRead
    validation_errors: list[UploadValidationError]


class UploadList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[UploadRead]


class CompanyRead(UTCReadModel):
    id: UUID
    upload_id: UUID
    raw_url: str
    normalized_url: str
    domain: str
    pipeline_stage: str
    created_at: datetime


class UploadCompanyList(BaseModel):
    upload_id: UUID
    total: int
    limit: int
    offset: int
    items: list[CompanyRead]


class CompanyListItem(UTCReadModel):
    id: UUID
    upload_id: UUID
    upload_filename: str
    raw_url: str
    normalized_url: str
    domain: str
    pipeline_stage: str
    created_at: datetime
    latest_decision: str | None = None
    latest_confidence: Decimal | None = None
    latest_scrape_job_id: UUID | None = None
    latest_scrape_status: str | None = None
    latest_scrape_terminal: bool | None = None
    latest_analysis_run_id: UUID | None = None
    latest_analysis_job_id: UUID | None = None
    latest_analysis_status: str | None = None
    latest_analysis_terminal: bool | None = None
    feedback_thumbs: str | None = None
    feedback_comment: str | None = None
    feedback_manual_label: str | None = None
    latest_scrape_error_code: str | None = None
    contact_count: int = 0
    contact_fetch_status: str | None = None


class CompanyList(BaseModel):
    total: int | None = None
    has_more: bool
    limit: int
    offset: int
    items: list[CompanyListItem]


class CompanyDeleteRequest(BaseModel):
    company_ids: list[UUID] = Field(min_length=1)


class CompanyDeleteResult(BaseModel):
    requested_count: int
    deleted_count: int
    deleted_ids: list[UUID]
    missing_ids: list[UUID]


class CompanyScrapeRequest(BaseModel):
    company_ids: list[UUID] = Field(min_length=1)
    scrape_rules: ScrapeRules | None = None
    upload_id: UUID | None = None


class CompanyScrapeAllRequest(BaseModel):
    upload_id: UUID | None = None
    scrape_rules: ScrapeRules | None = None


class CompanyScrapeResult(BaseModel):
    requested_count: int
    queued_count: int
    queued_job_ids: list[UUID]
    failed_company_ids: list[UUID]
    idempotency_key: str | None = None
    idempotency_replayed: bool = False


class CompanyIdsResult(BaseModel):
    ids: list[UUID]
    total: int


class CompanyCounts(BaseModel):
    total: int
    uploaded: int
    scraped: int
    classified: int
    contact_ready: int
    unlabeled: int
    possible: int
    unknown: int
    crap: int
    scrape_done: int
    scrape_failed: int
    not_scraped: int


class LetterCounts(BaseModel):
    counts: dict[str, int]  # 26 entries, 'a'..'z', zeros included
