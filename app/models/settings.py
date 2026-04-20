from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.pipeline import utcnow


class IntegrationProvider(StrEnum):
    OPENROUTER = "openrouter"
    SNOV = "snov"
    APOLLO = "apollo"
    ZEROBOUNCE = "zerobounce"


class IntegrationSecret(SQLModel, table=True):
    """Global encrypted secrets for external integrations.

    Secrets are stored as opaque ciphertext blobs encrypted with a Fernet key
    derived from PS_SETTINGS_ENCRYPTION_KEY. Plaintext never hits the DB.

    Keyed by (provider, field_name) so a single provider can have multiple
    credential fields (e.g. Snov has client_id + client_secret).
    """

    __tablename__ = "integration_secrets"
    __table_args__ = (
        UniqueConstraint("provider", "field_name", name="uq_integration_secrets_provider_field"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    provider: str = Field(max_length=64, index=True)
    field_name: str = Field(max_length=64, index=True)
    ciphertext: str = Field(sa_column=Column(Text, nullable=False))
    last4: str | None = Field(default=None, max_length=8)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
