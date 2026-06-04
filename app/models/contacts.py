from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, JSON
from sqlmodel import Field, SQLModel

from app.models.base import utc_datetime_field, utcnow


class RoleFetchCriteria(SQLModel, table=True):
    """
    Current editable title/role targeting rules for a campaign.
    EmailFetchBatch snapshots these criteria at enqueue time so historical
    fetches remain explainable after the current campaign criteria changes.
    """

    __tablename__ = "role_fetch_criteria"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    name: str = Field(max_length=255)
    include_rules_json: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    exclude_rules_json: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    criteria_hash: str = Field(max_length=64, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)


class EmailFetchBatch(SQLModel, table=True):
    """One operator action to fetch emails for a set of domains in a campaign."""

    __tablename__ = "email_fetch_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    role_fetch_criteria_id: UUID | None = Field(
        default=None, foreign_key="role_fetch_criteria.id", index=True
    )
    criteria_snapshot_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    criteria_hash: str | None = Field(default=None, max_length=64)
    provider_order_json: list[str] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    selected_domain_ids_json: list[str] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    result_summary_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    state: str = Field(default="queued", max_length=32, index=True)
    selected_domain_count: int = Field(default=0, ge=0)
    queued_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    finished_at: datetime | None = utc_datetime_field(default=None, nullable=True)


class EmailVerificationCache(SQLModel, table=True):
    """Provider verification results cached by normalized email."""

    __tablename__ = "email_verification_cache"
    __table_args__ = (
        Index(
            "ux_email_verification_cache_provider_email",
            "provider",
            "normalized_email",
            unique=True,
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    provider: str = Field(default="zerobounce", max_length=32, index=True)
    normalized_email: str = Field(max_length=512, index=True)
    status: str = Field(max_length=32, index=True)
    sub_status: str | None = Field(default=None, max_length=64)
    raw_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    validated_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    updated_at: datetime = utc_datetime_field(default_factory=utcnow)


class VerificationBatch(SQLModel, table=True):
    """One operator action to verify a set of contact emails via ZeroBounce."""

    __tablename__ = "verification_batches"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    state: str = Field(default="queued", max_length=32, index=True)
    selected_count: int = Field(default=0, ge=0)
    queued_count: int = Field(default=0, ge=0)
    verified_count: int = Field(default=0, ge=0)
    valid_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    selected_contact_snapshots_json: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    result_summary_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    finished_at: datetime | None = utc_datetime_field(default=None, nullable=True)


class Contact(SQLModel, table=True):
    """
    One row per person per campaign. Apollo and Snov data stored in separate columns.
    selected_email is the single authoritative email used by S4.

    Verification snapshot safety: S4 snapshots selected_email into verified_email_snapshot
    at enqueue time. On result write-back it only applies if selected_email still matches
    the snapshot, guarding against concurrent S3 runs changing the email mid-flight.
    """

    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_campaign_domain", "campaign_id", "domain_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    domain_id: UUID = Field(foreign_key="uploaded_domains.id", index=True)
    email_fetch_batch_id: UUID | None = Field(
        default=None, foreign_key="email_fetch_batches.id", index=True
    )
    criteria_hash: str | None = Field(default=None, max_length=64, index=True)

    # Identity
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    title: str | None = Field(default=None, max_length=512)
    linkedin_url: str | None = Field(default=None, max_length=2048)
    title_match: bool = Field(default=False, index=True)

    # Provider-specific identifiers and emails (evidence)
    apollo_person_id: str | None = Field(default=None, max_length=255, index=True)
    snov_person_id: str | None = Field(default=None, max_length=255, index=True)
    apollo_email: str | None = Field(default=None, max_length=512)
    snov_email: str | None = Field(default=None, max_length=512)
    provider_evidence_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    # Authoritative email — the only field S4 verifies
    selected_email: str | None = Field(default=None, max_length=512, index=True)
    selected_email_provider: str | None = Field(default=None, max_length=32)

    # Verification (S4) — folded in; no separate table needed
    verification_batch_id: UUID | None = Field(
        default=None, foreign_key="verification_batches.id", index=True
    )
    verified_email_snapshot: str | None = Field(default=None, max_length=512)
    verification_status: str | None = Field(default=None, max_length=32, index=True)
    verification_sub_status: str | None = Field(default=None, max_length=64)
    verification_raw_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    verification_applied: bool = Field(default=False)
    verified_at: datetime | None = utc_datetime_field(default=None, nullable=True)

    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    updated_at: datetime = utc_datetime_field(default_factory=utcnow)


class FetchedPerson(SQLModel, table=True):
    """
    Provider-returned person record from a confirmed S3 fetch.

    Contacts remain the qualified outreach/verification surface. This table is
    the transparency ledger for every person returned by paid provider searches,
    including people rejected by local title rules.
    """

    __tablename__ = "fetched_people"
    __table_args__ = (
        Index("ix_fetched_people_campaign_domain", "campaign_id", "domain_id"),
        Index("ix_fetched_people_batch_provider", "email_fetch_batch_id", "provider", "provider_person_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    campaign_id: UUID = Field(foreign_key="campaigns.id", index=True)
    domain_id: UUID = Field(foreign_key="uploaded_domains.id", index=True)
    email_fetch_batch_id: UUID | None = Field(
        default=None, foreign_key="email_fetch_batches.id", index=True
    )
    contact_id: UUID | None = Field(default=None, foreign_key="contacts.id", index=True)
    criteria_hash: str | None = Field(default=None, max_length=64, index=True)

    provider: str = Field(max_length=32, index=True)
    provider_person_id: str = Field(max_length=255, index=True)
    first_name: str = Field(default="", max_length=255)
    last_name: str = Field(default="", max_length=255)
    title: str | None = Field(default=None, max_length=512)
    linkedin_url: str | None = Field(default=None, max_length=2048)
    raw_summary_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    match_status: str = Field(default="not_matched", max_length=64, index=True)
    match_reason: str = Field(default="", max_length=512)
    email_lookup_attempted: bool = Field(default=False, index=True)
    email_result: str | None = Field(default=None, max_length=512)
    email_status: str | None = Field(default=None, max_length=64)
    email_error_code: str = Field(default="", max_length=128)
    email_raw_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    created_at: datetime = utc_datetime_field(default_factory=utcnow, index=True)
    updated_at: datetime = utc_datetime_field(default_factory=utcnow)
