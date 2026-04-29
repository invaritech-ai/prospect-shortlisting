from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScrapeJob(SQLModel, table=True):
    __table_args__ = (
        # Partial unique index: only one active (non-terminal) job per URL.
        sa.Index(
            "uq_scrapejob_active_normalized_url",
            "normalized_url",
            unique=True,
            postgresql_where=sa.text("terminal_state = false"),
            sqlite_where=sa.text("terminal_state = 0"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    pipeline_run_id: UUID | None = Field(default=None, foreign_key="pipeline_runs.id", index=True)
    website_url: str
    normalized_url: str
    domain: str

    # Lifecycle: created → running → succeeded / failed
    state: str = Field(default="created", index=True)
    terminal_state: bool = Field(default=False)
    failure_reason: Optional[str] = Field(default=None, max_length=128, index=True)

    # Per-job model config
    js_fallback: bool = Field(default=True)
    include_sitemap: bool = Field(default=True)
    general_model: str = Field(default="openai/gpt-5-nano")
    classify_model: str = Field(default="inception/mercury-2")

    # Counters
    discovered_urls_count: int = Field(default=0)
    pages_fetched_count: int = Field(default=0)
    fetch_failures_count: int = Field(default=0)
    markdown_pages_count: int = Field(default=0)
    llm_used_count: int = Field(default=0)
    llm_failed_count: int = Field(default=0)

    last_error_code: Optional[str] = Field(default=None)
    last_error_message: Optional[str] = Field(default=None)

    # Number of times the reconciler has reset and re-queued this job.
    # Used to cap infinite retry loops for consistently failing sites.
    reconcile_count: int = Field(default=0)

    # Ownership lock — set atomically at task-start via CAS; cleared on finish.
    # Guards against duplicate workers writing results when Celery re-delivers
    # a task (e.g. after soft_time_limit expiry or worker respawn).
    lock_token: Optional[str] = Field(default=None, max_length=64)
    lock_expires_at: Optional[datetime] = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)


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

    markdown_content: str = Field(default="")

    fetch_error_code: str = Field(default="")
    fetch_error_message: str = Field(default="")

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
