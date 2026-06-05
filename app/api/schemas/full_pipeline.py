from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.api.schemas.base import UTCReadModel


class FullPipelineCompanyRow(UTCReadModel):
    domain_id: UUID
    campaign_id: UUID
    raw_url: str
    normalized_url: str
    domain: str
    scrape_status: str | None
    decision_status: str | None
    fetch_status: str | None
    verify_status: str | None
    created_at: datetime
    latest_scrape_updated_at: datetime | None = None
    latest_scrape_error_code: str | None = None
    latest_scrape_failure_class: str | None = None
    latest_scrape_retryable: bool | None = None
    latest_scrape_final_url: str | None = None
    classification_state: str | None = None
    effective_label: str | None = None
    contacts_found: int = 0
    emails_found: int = 0
    email_contact_count: int = 0
    valid_email_count: int = 0
    latest_contact_updated_at: datetime | None = None
    last_activity: datetime


class FullPipelineCompanyList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[FullPipelineCompanyRow]
