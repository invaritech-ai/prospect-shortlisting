from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ScrapeJobCreate(BaseModel):
    website_url: str = Field(min_length=3, max_length=2048)
    js_fallback: bool = True
    include_sitemap: bool = True
    general_model: str = Field(
        default="openai/gpt-5-nano", min_length=2, max_length=128
    )
    classify_model: str = Field(
        default="inception/mercury-2", min_length=2, max_length=128
    )

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_markdown_model(cls, data: Any) -> Any:
        if isinstance(data, dict) and "general_model" not in data and "markdown_model" in data:
            data = dict(data)
            data["general_model"] = data["markdown_model"]
        return data


class ScrapeJobRead(BaseModel):
    id: UUID
    website_url: str
    normalized_url: str
    domain: str
    status: str
    terminal_state: bool
    js_fallback: bool
    include_sitemap: bool
    general_model: str
    classify_model: str
    discovered_urls_count: int
    pages_fetched_count: int
    fetch_failures_count: int
    markdown_pages_count: int
    llm_used_count: int
    llm_failed_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScrapePageRead(BaseModel):
    id: int
    job_id: UUID
    url: str
    canonical_url: str
    depth: int
    page_kind: str
    fetch_mode: str
    status_code: int
    title: str
    description: str
    text_len: int
    fetch_error_code: str
    fetch_error_message: str
    updated_at: datetime


class ScrapePageContentRead(BaseModel):
    id: int
    job_id: UUID
    url: str
    page_kind: str
    status_code: int
    markdown_content: str
    fetch_error_code: str
    fetch_error_message: str
    updated_at: datetime


class JobActionResult(BaseModel):
    job: ScrapeJobRead
    message: str


class JobEnqueueResult(BaseModel):
    job_id: UUID
    celery_task_id: str
    message: str
