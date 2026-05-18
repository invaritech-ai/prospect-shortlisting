from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


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
    by_stage: dict[str, PipelineStageCostRead] = Field(default_factory=dict)
