"""repair contact pipeline schema layer

Revision ID: dc4662e17bfb
Revises: 8b1c2d3e4f5a
Create Date: 2026-04-24

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
import sqlmodel.sql.sqltypes
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "dc4662e17bfb"
down_revision: Union[str, Sequence[str], None] = "8b1c2d3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONTACT_REVEAL_JOB_STATE_VALUES = ("queued", "running", "succeeded", "failed", "dead")


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return _table_exists(inspector, table_name) and any(
        column["name"] == column_name for column in inspector.get_columns(table_name)
    )


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return _table_exists(inspector, table_name) and any(
        index["name"] == index_name for index in inspector.get_indexes(table_name)
    )


def _unique_exists(inspector: sa.Inspector, table_name: str, unique_name: str) -> bool:
    return _table_exists(inspector, table_name) and any(
        unique["name"] == unique_name for unique in inspector.get_unique_constraints(table_name)
    )


def _ensure_pg_enum(bind, enum_name: str, labels: tuple[str, ...]) -> None:
    PGEnum(*labels, name=enum_name).create(bind, checkfirst=True)


def _add_column_with_temp_default_if_missing(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    column_type: sa.types.TypeEngine,
    default_clause,
) -> None:
    if _column_exists(inspector, table_name, column_name):
        return

    op.add_column(
        table_name,
        sa.Column(column_name, column_type, nullable=True, server_default=default_clause),
    )
    op.alter_column(
        table_name,
        column_name,
        existing_type=column_type,
        nullable=False,
        server_default=None,
    )


def _create_index_if_missing(
    inspector: sa.Inspector,
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if _index_exists(inspector, table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def _create_unique_if_missing(
    inspector: sa.Inspector,
    unique_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    if _unique_exists(inspector, table_name, unique_name):
        return
    op.create_unique_constraint(unique_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Ensure the enum used by contact_reveal_jobs exists before creating the table.
    _ensure_pg_enum(bind, "contactrevealjobstate", CONTACT_REVEAL_JOB_STATE_VALUES)

    if not _table_exists(inspector, "discovered_contacts"):
        op.create_table(
            "discovered_contacts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("contact_fetch_job_id", sa.Uuid(), nullable=True),
            sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
            sa.Column("provider_person_id", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("first_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("last_name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
            sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
            sa.Column("title_match", sa.Boolean(), nullable=False),
            sa.Column("linkedin_url", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=True),
            sa.Column("source_url", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=True),
            sa.Column("provider_has_email", sa.Boolean(), nullable=True),
            sa.Column("provider_metadata_json", sa.JSON(), nullable=True),
            sa.Column("raw_payload_json", sa.JSON(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("backfilled", sa.Boolean(), nullable=False),
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["contact_fetch_job_id"], ["contact_fetch_jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", "provider", "provider_person_id", name="uq_discovered_contacts_provider_key"),
        )

    if not _table_exists(inspector, "contact_reveal_batches"):
        op.create_table(
            "contact_reveal_batches",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("campaign_id", sa.Uuid(), nullable=False),
            sa.Column("trigger_source", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
            sa.Column("reveal_scope", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
            sa.Column("state", sa.Text(), nullable=False),
            sa.Column("requested_count", sa.Integer(), nullable=False),
            sa.Column("queued_count", sa.Integer(), nullable=False),
            sa.Column("already_revealing_count", sa.Integer(), nullable=False),
            sa.Column("skipped_revealed_count", sa.Integer(), nullable=False),
            sa.Column("last_error_code", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
            sa.Column("last_error_message", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists(inspector, "contact_reveal_jobs"):
        op.create_table(
            "contact_reveal_jobs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("contact_reveal_batch_id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("group_key", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
            sa.Column("discovered_contact_ids_json", sa.JSON(), nullable=False),
            sa.Column("requested_providers_json", sa.JSON(), nullable=False),
            sa.Column(
                "state",
                PGEnum(*CONTACT_REVEAL_JOB_STATE_VALUES, name="contactrevealjobstate", create_type=False),
                nullable=False,
            ),
            sa.Column("terminal_state", sa.Boolean(), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("last_error_code", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
            sa.Column("last_error_message", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=True),
            sa.Column("lock_token", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
            sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revealed_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["contact_reveal_batch_id"], ["contact_reveal_batches.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists(inspector, "contact_reveal_attempts"):
        op.create_table(
            "contact_reveal_attempts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("contact_reveal_job_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
            sa.Column("sequence_index", sa.Integer(), nullable=False),
            sa.Column("state", sa.Text(), nullable=False),
            sa.Column("terminal_state", sa.Boolean(), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("last_error_code", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
            sa.Column("last_error_message", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=True),
            sa.Column("deferred_reason", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("lock_token", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
            sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revealed_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["contact_reveal_job_id"], ["contact_reveal_jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("contact_reveal_job_id", "provider", name="uq_contact_reveal_attempts_job_provider"),
        )

    _add_column_with_temp_default_if_missing(
        inspector,
        "contact_fetch_batches",
        "force_refresh",
        sa.Boolean(),
        sa.false(),
    )
    _add_column_with_temp_default_if_missing(
        inspector,
        "contact_fetch_batches",
        "reused_count",
        sa.Integer(),
        sa.text("0"),
    )
    _add_column_with_temp_default_if_missing(
        inspector,
        "contact_fetch_batches",
        "stale_reused_count",
        sa.Integer(),
        sa.text("0"),
    )

    _add_column_with_temp_default_if_missing(
        inspector,
        "contact_fetch_runtime_controls",
        "reveal_enabled",
        sa.Boolean(),
        sa.true(),
    )
    _add_column_with_temp_default_if_missing(
        inspector,
        "contact_fetch_runtime_controls",
        "reveal_paused",
        sa.Boolean(),
        sa.false(),
    )
    _add_column_with_temp_default_if_missing(
        inspector,
        "contact_fetch_runtime_controls",
        "reveal_dispatcher_batch_size",
        sa.Integer(),
        sa.text("50"),
    )

    # Refresh the inspector so the post-create index/constraint checks can see
    # the tables created by this migration.
    inspector = sa.inspect(bind)

    # Indexes and unique constraints for the repaired schema layer.
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_id"), "discovered_contacts", ["id"])
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_company_id"), "discovered_contacts", ["company_id"])
    _create_index_if_missing(
        inspector,
        op.f("ix_discovered_contacts_contact_fetch_job_id"),
        "discovered_contacts",
        ["contact_fetch_job_id"],
    )
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_provider"), "discovered_contacts", ["provider"])
    _create_index_if_missing(
        inspector,
        op.f("ix_discovered_contacts_provider_person_id"),
        "discovered_contacts",
        ["provider_person_id"],
    )
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_title_match"), "discovered_contacts", ["title_match"])
    _create_index_if_missing(
        inspector,
        op.f("ix_discovered_contacts_provider_has_email"),
        "discovered_contacts",
        ["provider_has_email"],
    )
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_is_active"), "discovered_contacts", ["is_active"])
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_backfilled"), "discovered_contacts", ["backfilled"])
    _create_index_if_missing(
        inspector,
        op.f("ix_discovered_contacts_discovered_at"),
        "discovered_contacts",
        ["discovered_at"],
    )
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_last_seen_at"), "discovered_contacts", ["last_seen_at"])
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_created_at"), "discovered_contacts", ["created_at"])
    _create_index_if_missing(inspector, op.f("ix_discovered_contacts_updated_at"), "discovered_contacts", ["updated_at"])
    _create_unique_if_missing(
        inspector,
        "uq_discovered_contacts_provider_key",
        "discovered_contacts",
        ["company_id", "provider", "provider_person_id"],
    )

    _create_index_if_missing(inspector, op.f("ix_contact_reveal_batches_id"), "contact_reveal_batches", ["id"])
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_reveal_batches_campaign_id"),
        "contact_reveal_batches",
        ["campaign_id"],
    )
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_reveal_batches_trigger_source"),
        "contact_reveal_batches",
        ["trigger_source"],
    )
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_batches_reveal_scope"), "contact_reveal_batches", ["reveal_scope"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_batches_state"), "contact_reveal_batches", ["state"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_batches_created_at"), "contact_reveal_batches", ["created_at"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_batches_updated_at"), "contact_reveal_batches", ["updated_at"])

    _create_index_if_missing(inspector, op.f("ix_contact_reveal_jobs_id"), "contact_reveal_jobs", ["id"])
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_reveal_jobs_contact_reveal_batch_id"),
        "contact_reveal_jobs",
        ["contact_reveal_batch_id"],
    )
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_jobs_company_id"), "contact_reveal_jobs", ["company_id"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_jobs_group_key"), "contact_reveal_jobs", ["group_key"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_jobs_state"), "contact_reveal_jobs", ["state"])
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_reveal_jobs_lock_expires_at"),
        "contact_reveal_jobs",
        ["lock_expires_at"],
    )
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_jobs_created_at"), "contact_reveal_jobs", ["created_at"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_jobs_updated_at"), "contact_reveal_jobs", ["updated_at"])

    _create_index_if_missing(inspector, op.f("ix_contact_reveal_attempts_id"), "contact_reveal_attempts", ["id"])
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_reveal_attempts_contact_reveal_job_id"),
        "contact_reveal_attempts",
        ["contact_reveal_job_id"],
    )
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_attempts_provider"), "contact_reveal_attempts", ["provider"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_attempts_state"), "contact_reveal_attempts", ["state"])
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_reveal_attempts_next_retry_at"),
        "contact_reveal_attempts",
        ["next_retry_at"],
    )
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_reveal_attempts_lock_expires_at"),
        "contact_reveal_attempts",
        ["lock_expires_at"],
    )
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_attempts_created_at"), "contact_reveal_attempts", ["created_at"])
    _create_index_if_missing(inspector, op.f("ix_contact_reveal_attempts_updated_at"), "contact_reveal_attempts", ["updated_at"])
    _create_unique_if_missing(
        inspector,
        "uq_contact_reveal_attempts_job_provider",
        "contact_reveal_attempts",
        ["contact_reveal_job_id", "provider"],
    )

    _create_index_if_missing(
        inspector,
        op.f("ix_contact_fetch_batches_force_refresh"),
        "contact_fetch_batches",
        ["force_refresh"],
    )
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_fetch_runtime_controls_reveal_enabled"),
        "contact_fetch_runtime_controls",
        ["reveal_enabled"],
    )
    _create_index_if_missing(
        inspector,
        op.f("ix_contact_fetch_runtime_controls_reveal_paused"),
        "contact_fetch_runtime_controls",
        ["reveal_paused"],
    )


def downgrade() -> None:
    """Schema repair migrations are forward-only."""
    pass
