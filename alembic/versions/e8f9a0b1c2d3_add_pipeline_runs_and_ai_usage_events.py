"""add pipeline runs and ai usage events

Revision ID: e8f9a0b1c2d3
Revises: b0a1c2d3e4f5
Create Date: 2026-04-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "b0a1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("company_ids_snapshot", sa.JSON(), nullable=False),
        sa.Column("scrape_rules_snapshot", sa.JSON(), nullable=True),
        sa.Column("analysis_prompt_snapshot", sa.JSON(), nullable=True),
        sa.Column("contact_rules_snapshot", sa.JSON(), nullable=True),
        sa.Column("validation_policy_snapshot", sa.JSON(), nullable=True),
        sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reused_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_runs_id"), "pipeline_runs", ["id"], unique=False)
    op.create_index(op.f("ix_pipeline_runs_campaign_id"), "pipeline_runs", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_pipeline_runs_status"), "pipeline_runs", ["status"], unique=False)
    op.create_index(op.f("ix_pipeline_runs_created_at"), "pipeline_runs", ["created_at"], unique=False)
    op.create_index(op.f("ix_pipeline_runs_updated_at"), "pipeline_runs", ["updated_at"], unique=False)

    op.create_table(
        "pipeline_run_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_run_events_pipeline_run_id"), "pipeline_run_events", ["pipeline_run_id"], unique=False)
    op.create_index(op.f("ix_pipeline_run_events_company_id"), "pipeline_run_events", ["company_id"], unique=False)
    op.create_index(op.f("ix_pipeline_run_events_stage"), "pipeline_run_events", ["stage"], unique=False)
    op.create_index(op.f("ix_pipeline_run_events_created_at"), "pipeline_run_events", ["created_at"], unique=False)

    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="openrouter"),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("openrouter_generation_id", sa.String(length=255), nullable=True),
        sa.Column("billed_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_usage_events_id"), "ai_usage_events", ["id"], unique=False)
    op.create_index(op.f("ix_ai_usage_events_pipeline_run_id"), "ai_usage_events", ["pipeline_run_id"], unique=False)
    op.create_index(op.f("ix_ai_usage_events_campaign_id"), "ai_usage_events", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_ai_usage_events_company_id"), "ai_usage_events", ["company_id"], unique=False)
    op.create_index(op.f("ix_ai_usage_events_stage"), "ai_usage_events", ["stage"], unique=False)
    op.create_index(
        op.f("ix_ai_usage_events_openrouter_generation_id"),
        "ai_usage_events",
        ["openrouter_generation_id"],
        unique=False,
    )
    op.create_index(op.f("ix_ai_usage_events_reconciliation_status"), "ai_usage_events", ["reconciliation_status"], unique=False)
    op.create_index(op.f("ix_ai_usage_events_created_at"), "ai_usage_events", ["created_at"], unique=False)

    op.add_column("scrapejob", sa.Column("pipeline_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_scrapejob_pipeline_run_id_pipeline_runs",
        "scrapejob",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
    )
    op.create_index(op.f("ix_scrapejob_pipeline_run_id"), "scrapejob", ["pipeline_run_id"], unique=False)

    op.add_column("analysis_jobs", sa.Column("pipeline_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_analysis_jobs_pipeline_run_id_pipeline_runs",
        "analysis_jobs",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
    )
    op.create_index(op.f("ix_analysis_jobs_pipeline_run_id"), "analysis_jobs", ["pipeline_run_id"], unique=False)

    op.add_column("contact_fetch_jobs", sa.Column("pipeline_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_contact_fetch_jobs_pipeline_run_id_pipeline_runs",
        "contact_fetch_jobs",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
    )
    op.create_index(op.f("ix_contact_fetch_jobs_pipeline_run_id"), "contact_fetch_jobs", ["pipeline_run_id"], unique=False)

    op.add_column("contact_verify_jobs", sa.Column("pipeline_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_contact_verify_jobs_pipeline_run_id_pipeline_runs",
        "contact_verify_jobs",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
    )
    op.create_index(op.f("ix_contact_verify_jobs_pipeline_run_id"), "contact_verify_jobs", ["pipeline_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_contact_verify_jobs_pipeline_run_id"), table_name="contact_verify_jobs")
    op.drop_constraint("fk_contact_verify_jobs_pipeline_run_id_pipeline_runs", "contact_verify_jobs", type_="foreignkey")
    op.drop_column("contact_verify_jobs", "pipeline_run_id")

    op.drop_index(op.f("ix_contact_fetch_jobs_pipeline_run_id"), table_name="contact_fetch_jobs")
    op.drop_constraint("fk_contact_fetch_jobs_pipeline_run_id_pipeline_runs", "contact_fetch_jobs", type_="foreignkey")
    op.drop_column("contact_fetch_jobs", "pipeline_run_id")

    op.drop_index(op.f("ix_analysis_jobs_pipeline_run_id"), table_name="analysis_jobs")
    op.drop_constraint("fk_analysis_jobs_pipeline_run_id_pipeline_runs", "analysis_jobs", type_="foreignkey")
    op.drop_column("analysis_jobs", "pipeline_run_id")

    op.drop_index(op.f("ix_scrapejob_pipeline_run_id"), table_name="scrapejob")
    op.drop_constraint("fk_scrapejob_pipeline_run_id_pipeline_runs", "scrapejob", type_="foreignkey")
    op.drop_column("scrapejob", "pipeline_run_id")

    op.drop_index(op.f("ix_ai_usage_events_created_at"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_reconciliation_status"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_openrouter_generation_id"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_stage"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_company_id"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_campaign_id"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_pipeline_run_id"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_id"), table_name="ai_usage_events")
    op.drop_table("ai_usage_events")

    op.drop_index(op.f("ix_pipeline_run_events_created_at"), table_name="pipeline_run_events")
    op.drop_index(op.f("ix_pipeline_run_events_stage"), table_name="pipeline_run_events")
    op.drop_index(op.f("ix_pipeline_run_events_company_id"), table_name="pipeline_run_events")
    op.drop_index(op.f("ix_pipeline_run_events_pipeline_run_id"), table_name="pipeline_run_events")
    op.drop_table("pipeline_run_events")

    op.drop_index(op.f("ix_pipeline_runs_updated_at"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_created_at"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_status"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_campaign_id"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_id"), table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
