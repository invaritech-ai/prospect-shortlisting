from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.base import UTCReadModel


ProviderId = Literal["openrouter", "snov", "apollo", "zerobounce"]
CredentialSource = Literal["db", "env", ""]


class IntegrationFieldStatus(UTCReadModel):
    """Masked read shape for a single credential field."""

    field: str
    is_set: bool = False
    source: CredentialSource = ""
    last4: str | None = None
    updated_at: datetime | None = None


class IntegrationProviderStatus(UTCReadModel):
    provider: ProviderId
    label: str
    description: str
    fields: list[IntegrationFieldStatus]


class IntegrationsStatusResponse(UTCReadModel):
    store_available: bool
    providers: list[IntegrationProviderStatus]


class IntegrationFieldUpdate(BaseModel):
    field: str = Field(min_length=1, max_length=64)
    value: str = Field(default="", max_length=4096)


class IntegrationProviderUpdateRequest(BaseModel):
    fields: list[IntegrationFieldUpdate] = Field(default_factory=list)


class IntegrationTestResponse(BaseModel):
    provider: ProviderId
    ok: bool
    source: CredentialSource = ""
    error_code: str = ""
    message: str = ""
