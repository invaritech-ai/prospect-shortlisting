from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.base import UTCReadModel
from app.api.schemas.scrape import ScrapeRules


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    prompt_text: str = Field(min_length=1)
    enabled: bool = True
    scrape_pages_intent_text: str | None = Field(default=None, max_length=2000)


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    prompt_text: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    scrape_pages_intent_text: str | None = Field(default=None, max_length=2000)


class PromptRead(UTCReadModel):
    id: UUID
    name: str
    enabled: bool
    prompt_text: str
    scrape_pages_intent_text: str | None = None
    scrape_rules_structured: ScrapeRules | None = None
    created_at: datetime
    run_count: int = 0
