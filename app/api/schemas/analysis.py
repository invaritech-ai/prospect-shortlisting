from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator


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


class FeedbackUpsert(BaseModel):
    thumbs: str | None = None  # 'up' | 'down' | None
    comment: str | None = None
    manual_label: str | None = None  # 'possible' | 'unknown' | 'crap' | None

    @field_validator("thumbs")
    @classmethod
    def validate_thumbs(cls, v: str | None) -> str | None:
        if v is not None and v not in ("up", "down"):
            raise ValueError("thumbs must be 'up', 'down', or null")
        return v

    @field_validator("manual_label")
    @classmethod
    def validate_manual_label(cls, v: str | None) -> str | None:
        if v is not None and v not in ("possible", "unknown", "crap"):
            raise ValueError("manual_label must be 'possible', 'unknown', 'crap', or null")
        return v


class FeedbackRead(BaseModel):
    thumbs: str | None = None
    comment: str | None = None
    manual_label: str | None = None
    updated_at: datetime


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
