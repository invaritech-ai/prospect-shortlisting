from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.base import UTCReadModel


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class CampaignRead(UTCReadModel):
    id: UUID
    name: str
    description: str | None = None
    upload_count: int = 0
    company_count: int = 0
    created_at: datetime
    updated_at: datetime


class CampaignList(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool
    items: list[CampaignRead]


class CampaignAssignUploadsRequest(BaseModel):
    upload_ids: list[UUID] = Field(min_length=1)
