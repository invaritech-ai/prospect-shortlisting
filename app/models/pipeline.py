from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Enum as SAEnum, Numeric, Text, UniqueConstraint, event
from sqlalchemy.orm.attributes import set_committed_value
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
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AnalysisJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


class PredictedLabel(StrEnum):
    POSSIBLE = "possible"
    CRAP = "crap"
    UNKNOWN = "unknown"


class JobType(StrEnum):
    CRAWL = "crawl"
    ANALYSIS = "analysis"
    CONTACT_FETCH = "contact_fetch"


class ContactFetchJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


class ContactFetchBatchState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED = "paused"


class ContactProviderAttemptState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEFERRED = "deferred"
    FAILED = "failed"
    DEAD = "dead"


class CompanyPipelineStage(StrEnum):
    UPLOADED = "uploaded"
    SCRAPED = "scraped"
    CLASSIFIED = "classified"
    CONTACT_READY = "contact_ready"



class ContactVerifyJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PipelineRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"


class PipelineStage(StrEnum):
    SCRAPE = "scrape"
    ANALYSIS = "analysis"
    CONTACTS = "contacts"
    VALIDATION = "validation"


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str = Field(max_length=255, index=True)
    description: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class Upload(SQLModel, table=True):
    __tablename__ = "uploads"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
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
    pipeline_stage: CompanyPipelineStage = Field(
        default=CompanyPipelineStage.UPLOADED,
        sa_column=Column(Text, nullable=False, index=True),
    )
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
    failure_reason: str | None = Field(default=None, max_length=128, index=True)
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


class ScrapePrompt(SQLModel, table=True):
    __tablename__ = "scrape_prompts"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    name: str = Field(max_length=255, index=True)
    enabled: bool = Field(default=True, index=True)
    is_system_default: bool = Field(default=False, index=True)
    is_active: bool = Field(default=False, index=True)
    intent_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    compiled_prompt_text: str = Field(sa_column=Column(Text, nullable=False))
    scrape_rules_structured: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    upload_id: UUID = Field(foreign_key="uploads.id", index=True)
    prompt_id: UUID = Field(foreign_key="prompts.id", index=True)
    general_model: str = Field(max_length=128)
    classify_model: str = Field(max_length=128)
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
    pipeline_run_id: UUID | None = Field(default=None, foreign_key="pipeline_runs.id", index=True)
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
    lock_expires_at: datetime | None = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ClassificationResult(SQLModel, table=True):
    __tablename__ = "classification_results"
    __table_args__ = (UniqueConstraint("analysis_job_id", name="uq_classification_results_analysis_job"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    analysis_job_id: UUID = Field(foreign_key="analysis_jobs.id", index=True)
    predicted_label: PredictedLabel = Field(index=True)
    confidence: Decimal | None = Field(default=None, sa_column=Column(Numeric(5, 4), nullable=True))
    reasoning_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    evidence_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    # SHA-256[:32] of (prompt_hash + ":" + context). Used to skip LLM re-calls when
    # content hasn't changed between runs. Null for results written before this feature.
    input_hash: str | None = Field(default=None, max_length=64, index=True)
    from_cache: bool = Field(default=False)
    is_stale: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class CompanyFeedback(SQLModel, table=True):
    __tablename__ = "company_feedback"

    company_id: UUID = Field(foreign_key="companies.id", primary_key=True)
    thumbs: str | None = Field(default=None, max_length=8)  # 'up' | 'down'
    comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    manual_label: str | None = Field(default=None, max_length=16)  # 'possible' | 'unknown' | 'crap'
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)



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


class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    state: PipelineRunStatus = Field(default=PipelineRunStatus.QUEUED, sa_column=Column(Text, nullable=False, index=True))
    company_ids_snapshot: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    scrape_rules_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    analysis_prompt_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    contact_rules_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    validation_policy_snapshot: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    requested_count: int = Field(default=0, ge=0)
    reused_count: int = Field(default=0, ge=0)
    queued_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PipelineRunEvent(SQLModel, table=True):
    __tablename__ = "pipeline_run_events"

    id: int | None = Field(default=None, primary_key=True)
    pipeline_run_id: UUID = Field(foreign_key="pipeline_runs.id", index=True)
    company_id: UUID | None = Field(default=None, foreign_key="companies.id", index=True)
    stage: str = Field(max_length=64, index=True)
    event_type: str = Field(max_length=128)
    payload_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AiUsageEvent(SQLModel, table=True):
    __tablename__ = "ai_usage_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    pipeline_run_id: UUID | None = Field(default=None, foreign_key="pipeline_runs.id", index=True)
    campaign_id: UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    company_id: UUID | None = Field(default=None, foreign_key="companies.id", index=True)
    stage: str = Field(max_length=64, index=True)
    attempt_number: int = Field(default=1, ge=1)
    provider: str = Field(default="openrouter", max_length=64)
    model: str | None = Field(default=None, max_length=255)
    request_id: str | None = Field(default=None, max_length=255)
    openrouter_generation_id: str | None = Field(default=None, max_length=255, index=True)
    billed_cost_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 6), nullable=True))
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    error_type: str | None = Field(default=None, max_length=128)
    reconciliation_status: str = Field(default="pending", max_length=32, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class ContactFetchRuntimeControl(SQLModel, table=True):
    """Singleton-style operator controls for the contact pipeline."""

    __tablename__ = "contact_fetch_runtime_controls"
    __table_args__ = (
        UniqueConstraint("singleton_key", name="uq_contact_fetch_runtime_controls_singleton_key"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    singleton_key: str = Field(default="default", max_length=32, index=True)
    auto_enqueue_enabled: bool = Field(default=True, index=True)
    auto_enqueue_paused: bool = Field(default=False, index=True)
    auto_enqueue_max_batch_size: int = Field(default=25, ge=1)
    auto_enqueue_max_active_per_run: int = Field(default=10, ge=1)
    dispatcher_batch_size: int = Field(default=50, ge=1)
    reveal_enabled: bool = Field(default=True, index=True)
    reveal_paused: bool = Field(default=False, index=True)
    reveal_dispatcher_batch_size: int = Field(default=50, ge=1)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContactFetchBatch(SQLModel, table=True):
    """A single operator or pipeline enqueue action for contact fetching."""

    __tablename__ = "contact_fetch_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    pipeline_run_id: UUID | None = Field(default=None, foreign_key="pipeline_runs.id", index=True)
    trigger_source: str = Field(default="manual", max_length=32, index=True)
    requested_provider_mode: str = Field(default="snov", max_length=16, index=True)
    auto_enqueued: bool = Field(default=False, index=True)
    force_refresh: bool = Field(default=False, index=True)
    state: ContactFetchBatchState = Field(
        default=ContactFetchBatchState.QUEUED,
        sa_column=Column(Text, nullable=False, index=True),
    )
    requested_count: int = Field(default=0, ge=0)
    queued_count: int = Field(default=0, ge=0)
    already_fetching_count: int = Field(default=0, ge=0)
    reused_count: int = Field(default=0, ge=0)
    stale_reused_count: int = Field(default=0, ge=0)
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContactFetchJob(SQLModel, table=True):
    """One contact-fetch task per company. CAS-locked, same pattern as AnalysisJob."""

    __tablename__ = "contact_fetch_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    contact_fetch_batch_id: UUID | None = Field(default=None, foreign_key="contact_fetch_batches.id", index=True)
    pipeline_run_id: UUID | None = Field(default=None, foreign_key="pipeline_runs.id", index=True)
    provider: str = Field(default="snov", max_length=32, index=True)
    next_provider: str | None = Field(default=None, max_length=32, index=True)
    requested_providers_json: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    auto_enqueued: bool = Field(default=False, index=True)

    state: ContactFetchJobState = Field(
        default=ContactFetchJobState.QUEUED,
        sa_column=Column(
            SAEnum(
                ContactFetchJobState,
                values_callable=lambda x: [e.value for e in x],
                name="contactfetchjobstate",
                create_type=False,
            ),
            default=ContactFetchJobState.QUEUED,
            nullable=False,
            index=True,
        ),
    )
    terminal_state: bool = Field(default=False)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)

    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)
    failure_reason: str | None = Field(default=None, max_length=128, index=True)

    lock_token: str | None = Field(default=None, max_length=64)
    lock_expires_at: datetime | None = Field(default=None, index=True)

    contacts_found: int = Field(default=0, ge=0)
    title_matched_count: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContactProviderAttempt(SQLModel, table=True):
    """Provider-specific execution record for a company-level fetch job."""

    __tablename__ = "contact_provider_attempts"
    __table_args__ = (
        UniqueConstraint("contact_fetch_job_id", "provider", name="uq_contact_provider_attempts_job_provider"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    contact_fetch_job_id: UUID = Field(foreign_key="contact_fetch_jobs.id", index=True)
    provider: str = Field(max_length=32, index=True)
    sequence_index: int = Field(default=0, ge=0)
    state: ContactProviderAttemptState = Field(
        default=ContactProviderAttemptState.QUEUED,
        sa_column=Column(Text, nullable=False, index=True),
    )
    terminal_state: bool = Field(default=False)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)
    failure_reason: str | None = Field(default=None, max_length=128, index=True)
    deferred_reason: str | None = Field(default=None, max_length=128)
    next_retry_at: datetime | None = Field(default=None, index=True)
    lock_token: str | None = Field(default=None, max_length=64)
    lock_expires_at: datetime | None = Field(default=None, index=True)
    contacts_found: int = Field(default=0, ge=0)
    title_matched_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContactRevealBatch(SQLModel, table=True):
    __tablename__ = "contact_reveal_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    trigger_source: str = Field(default="manual", max_length=32, index=True)
    reveal_scope: str = Field(default="selected", max_length=32, index=True)
    state: ContactFetchBatchState = Field(
        default=ContactFetchBatchState.QUEUED,
        sa_column=Column(Text, nullable=False, index=True),
    )
    selected_count: int = Field(default=0, ge=0)
    requested_count: int = Field(default=0, ge=0)
    queued_count: int = Field(default=0, ge=0)
    already_revealing_count: int = Field(default=0, ge=0)
    skipped_revealed_count: int = Field(default=0, ge=0)
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContactRevealJob(SQLModel, table=True):
    __tablename__ = "contact_reveal_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    contact_reveal_batch_id: UUID = Field(foreign_key="contact_reveal_batches.id", index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    group_key: str = Field(max_length=512, index=True)
    discovered_contact_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    requested_providers_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    state: ContactFetchJobState = Field(
        default=ContactFetchJobState.QUEUED,
        sa_column=Column(
            SAEnum(
                ContactFetchJobState,
                values_callable=lambda x: [e.value for e in x],
                name="contactrevealjobstate",
                create_type=False,
            ),
            default=ContactFetchJobState.QUEUED,
            nullable=False,
            index=True,
        ),
    )
    terminal_state: bool = Field(default=False)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)
    lock_token: str | None = Field(default=None, max_length=64)
    lock_expires_at: datetime | None = Field(default=None, index=True)
    revealed_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContactRevealAttempt(SQLModel, table=True):
    __tablename__ = "contact_reveal_attempts"
    __table_args__ = (
        UniqueConstraint("contact_reveal_job_id", "provider", name="uq_contact_reveal_attempts_job_provider"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    contact_reveal_job_id: UUID = Field(foreign_key="contact_reveal_jobs.id", index=True)
    provider: str = Field(max_length=32, index=True)
    sequence_index: int = Field(default=0, ge=0)
    state: ContactProviderAttemptState = Field(
        default=ContactProviderAttemptState.QUEUED,
        sa_column=Column(Text, nullable=False, index=True),
    )
    terminal_state: bool = Field(default=False)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)
    failure_reason: str | None = Field(default=None, max_length=128, index=True)
    deferred_reason: str | None = Field(default=None, max_length=128)
    next_retry_at: datetime | None = Field(default=None, index=True)
    lock_token: str | None = Field(default=None, max_length=64)
    lock_expires_at: datetime | None = Field(default=None, index=True)
    revealed_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContactVerifyJob(SQLModel, table=True):
    """Bulk ZeroBounce verification job over an explicit contact set or filter snapshot."""

    __tablename__ = "contact_verify_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    pipeline_run_id: UUID | None = Field(default=None, foreign_key="pipeline_runs.id", index=True)
    state: ContactVerifyJobState = Field(
        default=ContactVerifyJobState.QUEUED,
        sa_column=Column(Text, nullable=False, index=True),
    )
    terminal_state: bool = Field(default=False)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)

    last_error_code: str | None = Field(default=None, max_length=128)
    last_error_message: str | None = Field(default=None, max_length=4000)

    lock_token: str | None = Field(default=None, max_length=64)
    lock_expires_at: datetime | None = Field(default=None, index=True)

    filter_snapshot_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    contact_ids_json: list[str] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )

    selected_count: int = Field(default=0, ge=0)
    verified_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class Contact(SQLModel, table=True):
    """Unified contact record: fetch → title match → email reveal → verification."""

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("company_id", "source_provider", "provider_person_id", name="uq_contacts_provider_key"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    company_id: UUID = Field(foreign_key="companies.id", index=True)
    contact_fetch_job_id: UUID | None = Field(default=None, foreign_key="contact_fetch_jobs.id", index=True)
    source_provider: str = Field(max_length=32, index=True)
    provider_person_id: str = Field(max_length=255, index=True)
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    title: str | None = Field(default=None, max_length=512)
    title_match: bool = Field(default=False, index=True)
    linkedin_url: str | None = Field(default=None, max_length=2048)
    source_url: str | None = Field(default=None, max_length=2048)
    provider_has_email: bool | None = Field(default=None, index=True)
    provider_metadata_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    raw_payload_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    is_active: bool = Field(default=True, index=True)
    backfilled: bool = Field(default=False, index=True)

    # Email reveal
    email: str | None = Field(default=None, max_length=512, index=True)
    email_provider: str | None = Field(default=None, max_length=32)
    email_confidence: float | None = Field(default=None)
    provider_email_status: str | None = Field(default=None, max_length=32, index=True)
    reveal_raw_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    # Verification
    verification_status: str = Field(default="unverified", max_length=32, index=True)
    verification_provider: str | None = Field(default=None, max_length=32, index=True)
    zerobounce_raw: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    # Pipeline stage: fetched | email_revealed | campaign_ready
    pipeline_stage: str = Field(default="fetched", max_length=32, index=True)

    discovered_at: datetime = Field(default_factory=utcnow, index=True)
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class TitleMatchRule(SQLModel, table=True):
    """Keyword-set rules for matching prospect titles.

    rule_type='include': ALL keywords in the set must appear in the title (AND logic).
    rule_type='exclude': ANY keyword in the set disqualifies the title.
    Include rules are ORed together; exclude rules are checked before includes.
    """

    __tablename__ = "title_match_rules"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "rule_type",
            "match_type",
            "keywords",
            name="uq_title_match_rules_campaign_rule",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    # 'include' or 'exclude'
    rule_type: str = Field(max_length=16, index=True)
    # 'keyword' | 'regex' | 'seniority'
    match_type: str = Field(default="keyword", max_length=32)
    # Comma-separated keywords, regex pattern, or seniority preset name
    keywords: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=utcnow, index=True)


def coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_model_datetimes(target: Any) -> None:
    mapper = getattr(target, "__mapper__", None)
    if mapper is None:
        return
    for prop in mapper.column_attrs:
        value = getattr(target, prop.key, None)
        if isinstance(value, datetime):
            normalized = coerce_utc_datetime(value)
            if normalized != value:
                set_committed_value(target, prop.key, normalized)


@event.listens_for(SQLModel, "load", propagate=True)
def _normalize_loaded_model_datetimes(target: Any, _context: Any) -> None:
    _normalize_model_datetimes(target)


@event.listens_for(SQLModel, "refresh", propagate=True)
def _normalize_refreshed_model_datetimes(target: Any, _context: Any, _attrs: Any) -> None:
    _normalize_model_datetimes(target)
