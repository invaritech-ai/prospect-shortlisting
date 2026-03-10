from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Index, JSON, Column, Numeric, Text, UniqueConstraint
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CrawlJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


class PredictedLabel(StrEnum):
    POSSIBLE = "Possible"
    CRAP = "Crap"
    UNKNOWN = "Unknown"


class JobType(StrEnum):
    CRAWL = "crawl"
    ANALYSIS = "analysis"


class Upload(SQLModel, table=True):
    __tablename__ = "uploads"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    filename: str = Field(max_length=1024)
    checksum: str = Field(max_length=128, index=True)
    row_count: int = Field(default=0, ge=0)
    valid_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    validation_errors_json: list[dict[str, Any]] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Company(SQLModel, table=True):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("upload_id", "normalized_url", name="uq_companies_upload_normalized_url"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True)
    raw_url: str = Field(sa_column=Column(Text, nullable=False))
    normalized_url: str = Field(max_length=2048)
    domain: str = Field(max_length=255, index=True)
    source_row_number: int | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class CrawlJob(SQLModel, table=True):
    __tablename__ = "crawl_jobs"
    __table_args__ = (UniqueConstraint("upload_id", "company_id", name="uq_crawl_jobs_upload_company"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    state: CrawlJobState = Field(default=CrawlJobState.QUEUED, index=True)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class CrawlArtifact(SQLModel, table=True):
    __tablename__ = "crawl_artifacts"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    crawl_job_id: UUID = Field(foreign_key="crawl_jobs.id", index=True)

    home_url: str | None = Field(default=None, max_length=2048)
    about_url: str | None = Field(default=None, max_length=2048)
    product_url: str | None = Field(default=None, max_length=2048)

    home_status: int | None = Field(default=None, ge=0)
    about_status: int | None = Field(default=None, ge=0)
    product_status: int | None = Field(default=None, ge=0)

    home_markdown_uri: str | None = Field(default=None, max_length=4096)
    about_markdown_uri: str | None = Field(default=None, max_length=4096)
    product_markdown_uri: str | None = Field(default=None, max_length=4096)

    home_screenshot_uri: str | None = Field(default=None, max_length=4096)
    about_screenshot_uri: str | None = Field(default=None, max_length=4096)
    product_screenshot_uri: str | None = Field(default=None, max_length=4096)

    home_ocr_uri: str | None = Field(default=None, max_length=4096)
    about_ocr_uri: str | None = Field(default=None, max_length=4096)
    product_ocr_uri: str | None = Field(default=None, max_length=4096)

    created_at: datetime = Field(default_factory=utcnow, index=True)


class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str = Field(max_length=255, index=True)
    enabled: bool = Field(default=True, index=True)
    prompt_text: str
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True)
    prompt_id: UUID = Field(foreign_key="prompts.id", index=True)
    general_model: str = Field(max_length=128)
    classify_model: str = Field(max_length=128)
    ocr_model: str = Field(max_length=128)
    status: RunStatus = Field(default=RunStatus.CREATED, index=True)
    total_jobs: int = Field(default=0, ge=0)
    completed_jobs: int = Field(default=0, ge=0)
    failed_jobs: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AnalysisJob(SQLModel, table=True):
    __tablename__ = "analysis_jobs"
    __table_args__ = (UniqueConstraint("run_id", "company_id", name="uq_analysis_jobs_run_company"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    crawl_artifact_id: UUID = Field(foreign_key="crawl_artifacts.id", index=True)

    state: AnalysisJobState = Field(default=AnalysisJobState.QUEUED, index=True)
    terminal_state: bool = Field(default=False)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    prompt_hash: str = Field(max_length=128)

    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)

    # Idempotency / ownership lock — set atomically at job-start; guards against
    # duplicate workers writing results when the same task is delivered twice.
    lock_token: str | None = Field(default=None, max_length=64)
    lock_expires_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class ClassificationResult(SQLModel, table=True):
    __tablename__ = "classification_results"
    __table_args__ = (UniqueConstraint("analysis_job_id", name="uq_classification_results_analysis_job"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    analysis_job_id: UUID = Field(foreign_key="analysis_jobs.id", index=True)
    predicted_label: PredictedLabel = Field(index=True)
    confidence: Decimal | None = Field(default=None, sa_column=Column(Numeric(5, 4), nullable=True))
    reasoning_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    evidence_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class CompanyFeedback(SQLModel, table=True):
    __tablename__ = "company_feedback"

    company_id: UUID = Field(foreign_key="companies.id", primary_key=True)
    thumbs: str | None = Field(default=None, max_length=8)  # 'up' | 'down'
    comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class JobOutbox(SQLModel, table=True):
    __tablename__ = "job_outbox"
    __table_args__ = (
        Index(
            "ix_job_outbox_pending",
            "created_at",
            postgresql_where=sa_text("published_at IS NULL"),
        ),
        Index(
            "uq_job_outbox_pending",
            "job_id",
            "task_type",
            unique=True,
            postgresql_where=sa_text("published_at IS NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(nullable=False)
    task_type: str = Field(max_length=128, nullable=False)
    payload_json: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    published_at: datetime | None = Field(default=None)
    stream_id: str | None = Field(default=None, max_length=128)
    publish_attempts: int = Field(default=0, nullable=False)


class JobEvent(SQLModel, table=True):
    __tablename__ = "job_events"

    id: int | None = Field(default=None, primary_key=True)
    job_type: JobType = Field(index=True)
    job_id: UUID = Field(index=True)
    from_state: str | None = Field(default=None, max_length=64)
    to_state: str = Field(max_length=64)
    event_type: str = Field(max_length=128)
    payload_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow, index=True)
