from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.base import UTCReadModel


class ScrapePromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    intent_text: str | None = Field(default=None, max_length=4000)
    enabled: bool = True
    set_active: bool = False


class ScrapePromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    intent_text: str | None = Field(default=None, max_length=4000)
    enabled: bool | None = None


class ScrapePromptRead(UTCReadModel):
    id: UUID
    name: str
    enabled: bool
    is_system_default: bool
    is_active: bool
    intent_text: str | None = None
    compiled_prompt_text: str
    scrape_rules_structured: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
