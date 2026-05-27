from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.api.schemas.base import UTCReadModel


DecisionModelId = Literal[
    "inclusionai/ring-2.6-1t",
    "ibm-granite/granite-4.1-8b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "deepseek/deepseek-v4-flash",
    "inclusionai/ling-2.6-1t",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
]

DEFAULT_DECISION_MODEL: DecisionModelId = "inclusionai/ring-2.6-1t"


class DecisionSettingsRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    name: str
    instruction_text: str
    model: str
    settings_hash: str
    is_active: bool
    created_at: datetime


class DecisionSettingsCreate(BaseModel):
    campaign_id: UUID
    name: str = Field(default="Default", min_length=1, max_length=255)
    instruction_text: str = Field(min_length=1, max_length=200000)
    model: DecisionModelId = DEFAULT_DECISION_MODEL
    is_active: bool = True

    @field_validator("name", "instruction_text")
    @classmethod
    def _strip_and_validate(cls, value: str) -> str:
        v = value.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class DecisionSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    instruction_text: str | None = Field(default=None, min_length=1, max_length=200000)
    model: DecisionModelId | None = None
    is_active: bool | None = None

    @field_validator("name", "instruction_text")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class DecisionSettingsList(BaseModel):
    total: int
    items: list[DecisionSettingsRead]
