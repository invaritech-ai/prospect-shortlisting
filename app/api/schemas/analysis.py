from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AnalysisRunJobRead(BaseModel):
    analysis_job_id: UUID
    run_id: UUID
    company_id: UUID
    domain: str
    state: str
    terminal_state: bool
    last_error_code: str | None = None
    last_error_message: str | None = None
    predicted_label: str | None = None
    confidence: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AnalysisJobDetailRead(BaseModel):
    analysis_job_id: UUID
    run_id: UUID
    company_id: UUID
    domain: str
    state: str
    terminal_state: bool
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    prompt_name: str
    run_status: str
    predicted_label: str | None = None
    confidence: float | None = None
    reasoning_json: dict[str, Any] | None = None
    evidence_json: dict[str, Any] | None = None
