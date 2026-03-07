from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    prompt_text: str = Field(min_length=1)
    enabled: bool = True


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    prompt_text: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None


class PromptRead(BaseModel):
    id: UUID
    name: str
    enabled: bool
    prompt_text: str
    created_at: datetime
