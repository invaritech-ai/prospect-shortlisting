from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.pipeline import PipelineRunStatus


class PipelineRunStartRequest(BaseModel):
    campaign_id: UUID
    company_ids: list[str] | None = None
    scrape_rules_snapshot: dict[str, Any] | None = None
    analysis_prompt_snapshot: dict[str, Any] | None = None
    contact_rules_snapshot: dict[str, Any] | None = None
    validation_policy_snapshot: dict[str, Any] | None = None
    force_rerun: dict[str, bool] | None = None


class PipelineRunStartResponse(BaseModel):
    pipeline_run_id: UUID
    requested_count: int
    reused_count: int
    queued_count: int
    skipped_count: int
    failed_count: int


class PipelineStageProgressRead(BaseModel):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    total: int = 0


class PipelineRunProgressRead(BaseModel):
    pipeline_run_id: UUID
    campaign_id: UUID
    state: PipelineRunStatus
    requested_count: int
    reused_count: int
    queued_count: int
    skipped_count: int
    failed_count: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stages: dict[str, PipelineStageProgressRead]


class PipelineStageCostRead(BaseModel):
    cost_usd: Decimal = Decimal("0")
    event_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class PipelineCostSummaryRead(BaseModel):
    pipeline_run_id: UUID | None = None
    campaign_id: UUID | None = None
    company_id: UUID | None = None
    total_cost_usd: Decimal = Decimal("0")
    event_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_stage: dict[str, PipelineStageCostRead]


class CostReconciliationSummaryRead(BaseModel):
    total_events: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
