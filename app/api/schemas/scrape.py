from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.base import UTCReadModel

DEFAULT_STRUCTURED_RULES: dict[str, Any] = {
    "fallback_enabled": True,
    "fallback_limit": 1,
    "js_fallback": True,
    "include_sitemap": True,
}


# ── Settings ────────────────────────────────────────────────────────────────

class ScrapeSettingsRead(UTCReadModel):
    id: UUID
    campaign_id: UUID | None
    name: str
    instruction_text: str | None
    structured_rules_json: dict[str, Any] | None
    is_active: bool
    created_at: datetime


class ScrapeSettingsCreate(BaseModel):
    campaign_id: UUID
    name: str = Field(default="Default", max_length=255)
    instruction_text: str | None = None
    structured_rules_json: dict[str, Any] | None = None


class ScrapeSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    instruction_text: str | None = None
    structured_rules_json: dict[str, Any] | None = None
    is_active: bool | None = None


class ScrapeSettingsList(BaseModel):
    total: int
    items: list[ScrapeSettingsRead]


# ── Batches ──────────────────────────────────────────────────────────────────

class ScrapeBatchFilter(BaseModel):
    scrape_status: str | None = None   # 'pending' | 'failed' | 'done' | 'running'
    letter: str | None = None          # 'A'-'Z' | '#' | None = all


class ScrapeBatchCreate(BaseModel):
    campaign_id: UUID
    domain_ids: list[UUID] = Field(default_factory=list)
    filter: ScrapeBatchFilter | None = None


class ScrapeBatchRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    state: str
    selected_domain_count: int
    queued_count: int
    success_count: int
    failed_count: int
    created_at: datetime
    finished_at: datetime | None = None
    eta_seconds: float | None = None


class ScrapeBatchList(BaseModel):
    total: int
    items: list[ScrapeBatchRead]


# ── Results (per-domain scraped content) ─────────────────────────────────────

class ScrapeResultRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    domain_id: UUID
    scrape_batch_id: UUID | None
    state: str
    pages_attempted_count: int
    pages_success_count: int
    markdown_pages_count: int
    scraped_pages_json: list[dict[str, Any]] | None
    error_code: str | None
    failure_class: str | None = None
    retryable: bool | None = None
    final_url: str | None = None
    created_at: datetime
    updated_at: datetime


# ── Letter counts ─────────────────────────────────────────────────────────────

class LetterCountsResponse(BaseModel):
    counts: dict[str, int]
