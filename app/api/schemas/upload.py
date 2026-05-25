from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.api.schemas.base import UTCReadModel


class UploadRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    filename: str
    row_count: int
    created_at: datetime


class UploadCreateResult(BaseModel):
    upload: UploadRead
    new_count: int
    dupe_count: int


class UploadList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[UploadRead]


class DomainRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    upload_id: UUID | None
    raw_url: str
    normalized_url: str
    domain: str
    scrape_status: str | None
    decision_status: str | None
    fetch_status: str | None
    verify_status: str | None
    created_at: datetime
    latest_scrape_updated_at: datetime | None = None
    latest_scrape_result_id: UUID | None = None
    latest_scrape_error_code: str | None = None
    latest_scrape_failure_class: str | None = None
    latest_scrape_retryable: bool | None = None
    latest_scrape_final_url: str | None = None


class DomainList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DomainRead]
