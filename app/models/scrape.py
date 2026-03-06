from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScrapeJob(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    website_url: str
    normalized_url: str
    domain: str

    status: str = Field(default="created", index=True)
    stage1_status: str = Field(default="pending")
    stage2_status: str = Field(default="pending")
    terminal_state: bool = Field(default=False)

    max_pages: int = Field(default=60)
    max_depth: int = Field(default=3)
    js_fallback: bool = Field(default=True)
    include_sitemap: bool = Field(default=True)
    general_model: str = Field(default="openai/gpt-5-nano")
    classify_model: str = Field(default="inception/mercury-2")
    ocr_model: str = Field(default="google/gemini-3.1-flash-lite-preview")
    enable_ocr: bool = Field(default=True)
    max_images_per_page: int = Field(default=8)

    discovered_urls_count: int = Field(default=0)
    pages_fetched_count: int = Field(default=0)
    fetch_failures_count: int = Field(default=0)
    markdown_pages_count: int = Field(default=0)
    ocr_images_processed_count: int = Field(default=0)

    llm_used_count: int = Field(default=0)
    llm_failed_count: int = Field(default=0)

    last_error_code: Optional[str] = Field(default=None)
    last_error_message: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    step1_started_at: Optional[datetime] = Field(default=None)
    step1_finished_at: Optional[datetime] = Field(default=None)
    step2_started_at: Optional[datetime] = Field(default=None)
    step2_finished_at: Optional[datetime] = Field(default=None)


class ScrapePage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: UUID = Field(foreign_key="scrapejob.id", index=True)

    url: str
    canonical_url: str
    depth: int = Field(default=0)
    page_kind: str = Field(default="other")
    fetch_mode: str = Field(default="none")
    status_code: int = Field(default=0)

    title: str = Field(default="")
    description: str = Field(default="")
    text_len: int = Field(default=0)
    raw_text: str = Field(default="")
    html_snapshot: str = Field(default="")

    image_urls_json: str = Field(default="[]")
    ocr_text: str = Field(default="")
    markdown_content: str = Field(default="")

    fetch_error_code: str = Field(default="")
    fetch_error_message: str = Field(default="")

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
