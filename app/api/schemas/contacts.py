from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.api.schemas.base import UTCReadModel


class ContactRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    domain_id: UUID
    domain: str
    first_name: str
    last_name: str
    title: str | None
    linkedin_url: str | None
    title_match: bool
    selected_email: str | None
    selected_email_provider: str | None
    verification_status: str | None
    criteria_hash: str | None
    provider_evidence_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ContactList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ContactRead]


class FetchedPersonRead(UTCReadModel):
    id: UUID
    campaign_id: UUID
    domain_id: UUID
    domain: str
    email_fetch_batch_id: UUID | None
    contact_id: UUID | None
    criteria_hash: str | None
    provider: str
    provider_person_id: str
    first_name: str
    last_name: str
    title: str | None
    linkedin_url: str | None
    match_status: str
    match_reason: str
    email_lookup_attempted: bool
    email_result: str | None
    email_status: str | None
    email_error_code: str
    created_at: datetime
    updated_at: datetime


class FetchedPersonList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[FetchedPersonRead]
