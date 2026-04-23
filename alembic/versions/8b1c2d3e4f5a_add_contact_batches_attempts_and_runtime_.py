"""add contact batches, provider attempts, and runtime controls

Revision ID: 8b1c2d3e4f5a
Revises: 7c2e9a4f1b0d
Create Date: 2026-04-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8b1c2d3e4f5a"
down_revision: Union[str, Sequence[str], None] = "7c2e9a4f1b0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contact_fetch_runtime_controls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("singleton_key", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("auto_enqueue_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auto_enqueue_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_enqueue_max_batch_size", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("auto_enqueue_max_active_per_run", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("dispatcher_batch_size", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key", name="uq_contact_fetch_runtime_controls_singleton_key"),
    )
    op.create_index(
        op.f("ix_contact_fetch_runtime_controls_id"),
        "contact_fetch_runtime_controls",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contact_fetch_runtime_controls_singleton_key"),
        "contact_fetch_runtime_controls",
        ["singleton_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contact_fetch_runtime_controls_auto_enqueue_enabled"),
        "contact_fetch_runtime_controls",
        ["auto_enqueue_enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contact_fetch_runtime_controls_auto_enqueue_paused"),
        "contact_fetch_runtime_controls",
        ["auto_enqueue_paused"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contact_fetch_runtime_controls_created_at"),
        "contact_fetch_runtime_controls",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contact_fetch_runtime_controls_updated_at"),
        "contact_fetch_runtime_controls",
        ["updated_at"],
        unique=False,
    )

    op.create_table(
        "contact_fetch_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_source", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("requested_provider_mode", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("auto_enqueued", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("already_fetching_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("last_error_message", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contact_fetch_batches_id"), "contact_fetch_batches", ["id"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_campaign_id"), "contact_fetch_batches", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_pipeline_run_id"), "contact_fetch_batches", ["pipeline_run_id"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_trigger_source"), "contact_fetch_batches", ["trigger_source"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_requested_provider_mode"), "contact_fetch_batches", ["requested_provider_mode"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_auto_enqueued"), "contact_fetch_batches", ["auto_enqueued"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_state"), "contact_fetch_batches", ["state"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_created_at"), "contact_fetch_batches", ["created_at"], unique=False)
    op.create_index(op.f("ix_contact_fetch_batches_updated_at"), "contact_fetch_batches", ["updated_at"], unique=False)

    op.add_column("contact_fetch_jobs", sa.Column("contact_fetch_batch_id", sa.Uuid(), nullable=True))
    op.add_column("contact_fetch_jobs", sa.Column("requested_providers_json", sa.JSON(), nullable=True))
    op.add_column(
        "contact_fetch_jobs",
        sa.Column("auto_enqueued", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        op.f("ix_contact_fetch_jobs_contact_fetch_batch_id"),
        "contact_fetch_jobs",
        ["contact_fetch_batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contact_fetch_jobs_auto_enqueued"),
        "contact_fetch_jobs",
        ["auto_enqueued"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_contact_fetch_jobs_batch_id_batches",
        "contact_fetch_jobs",
        "contact_fetch_batches",
        ["contact_fetch_batch_id"],
        ["id"],
    )

    op.create_table(
        "contact_provider_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contact_fetch_job_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("terminal_state", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_error_code", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("last_error_message", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=True),
        sa.Column("deferred_reason", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_token", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contacts_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title_matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contact_fetch_job_id"], ["contact_fetch_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contact_fetch_job_id", "provider", name="uq_contact_provider_attempts_job_provider"),
    )
    op.create_index(op.f("ix_contact_provider_attempts_id"), "contact_provider_attempts", ["id"], unique=False)
    op.create_index(
        op.f("ix_contact_provider_attempts_contact_fetch_job_id"),
        "contact_provider_attempts",
        ["contact_fetch_job_id"],
        unique=False,
    )
    op.create_index(op.f("ix_contact_provider_attempts_provider"), "contact_provider_attempts", ["provider"], unique=False)
    op.create_index(op.f("ix_contact_provider_attempts_state"), "contact_provider_attempts", ["state"], unique=False)
    op.create_index(op.f("ix_contact_provider_attempts_next_retry_at"), "contact_provider_attempts", ["next_retry_at"], unique=False)
    op.create_index(op.f("ix_contact_provider_attempts_lock_expires_at"), "contact_provider_attempts", ["lock_expires_at"], unique=False)
    op.create_index(op.f("ix_contact_provider_attempts_created_at"), "contact_provider_attempts", ["created_at"], unique=False)
    op.create_index(op.f("ix_contact_provider_attempts_updated_at"), "contact_provider_attempts", ["updated_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_contact_provider_attempts_updated_at"), table_name="contact_provider_attempts")
    op.drop_index(op.f("ix_contact_provider_attempts_created_at"), table_name="contact_provider_attempts")
    op.drop_index(op.f("ix_contact_provider_attempts_lock_expires_at"), table_name="contact_provider_attempts")
    op.drop_index(op.f("ix_contact_provider_attempts_next_retry_at"), table_name="contact_provider_attempts")
    op.drop_index(op.f("ix_contact_provider_attempts_state"), table_name="contact_provider_attempts")
    op.drop_index(op.f("ix_contact_provider_attempts_provider"), table_name="contact_provider_attempts")
    op.drop_index(op.f("ix_contact_provider_attempts_contact_fetch_job_id"), table_name="contact_provider_attempts")
    op.drop_index(op.f("ix_contact_provider_attempts_id"), table_name="contact_provider_attempts")
    op.drop_table("contact_provider_attempts")

    op.drop_constraint(
        "fk_contact_fetch_jobs_batch_id_batches",
        "contact_fetch_jobs",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_contact_fetch_jobs_auto_enqueued"), table_name="contact_fetch_jobs")
    op.drop_index(op.f("ix_contact_fetch_jobs_contact_fetch_batch_id"), table_name="contact_fetch_jobs")
    op.drop_column("contact_fetch_jobs", "auto_enqueued")
    op.drop_column("contact_fetch_jobs", "requested_providers_json")
    op.drop_column("contact_fetch_jobs", "contact_fetch_batch_id")

    op.drop_index(op.f("ix_contact_fetch_batches_updated_at"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_created_at"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_state"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_auto_enqueued"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_requested_provider_mode"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_trigger_source"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_pipeline_run_id"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_campaign_id"), table_name="contact_fetch_batches")
    op.drop_index(op.f("ix_contact_fetch_batches_id"), table_name="contact_fetch_batches")
    op.drop_table("contact_fetch_batches")

    op.drop_index(
        op.f("ix_contact_fetch_runtime_controls_updated_at"),
        table_name="contact_fetch_runtime_controls",
    )
    op.drop_index(
        op.f("ix_contact_fetch_runtime_controls_created_at"),
        table_name="contact_fetch_runtime_controls",
    )
    op.drop_index(
        op.f("ix_contact_fetch_runtime_controls_auto_enqueue_paused"),
        table_name="contact_fetch_runtime_controls",
    )
    op.drop_index(
        op.f("ix_contact_fetch_runtime_controls_auto_enqueue_enabled"),
        table_name="contact_fetch_runtime_controls",
    )
    op.drop_index(
        op.f("ix_contact_fetch_runtime_controls_singleton_key"),
        table_name="contact_fetch_runtime_controls",
    )
    op.drop_index(op.f("ix_contact_fetch_runtime_controls_id"), table_name="contact_fetch_runtime_controls")
    op.drop_table("contact_fetch_runtime_controls")
