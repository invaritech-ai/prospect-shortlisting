from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class RunCreateRequest(BaseModel):
    prompt_id: UUID
    scope: Literal["all", "selected"] = "selected"
    company_ids: list[UUID] | None = None
    general_model: str = Field(default="openai/gpt-5-nano", min_length=2, max_length=128)
    classify_model: str = Field(default="inception/mercury-2", min_length=2, max_length=128)
    ocr_model: str = Field(default="google/gemini-3.1-flash-lite-preview", min_length=2, max_length=128)

    @model_validator(mode="after")
    def _validate_scope(self) -> "RunCreateRequest":
        if self.scope == "selected" and not self.company_ids:
            raise ValueError("company_ids are required when scope is selected.")
        return self


class RunRead(BaseModel):
    id: UUID
    upload_id: UUID
    prompt_id: UUID
    prompt_name: str
    general_model: str
    classify_model: str
    ocr_model: str
    status: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunCreateResult(BaseModel):
    requested_count: int
    queued_count: int
    skipped_company_ids: list[UUID]
    runs: list[RunRead]
