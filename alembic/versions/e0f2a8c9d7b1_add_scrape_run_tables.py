"""add scrape run dispatcher tables

Revision ID: e0f2a8c9d7b1
Revises: 7552eea89678
Create Date: 2026-05-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "e0f2a8c9d7b1"
down_revision: Union[str, Sequence[str], None] = "7552eea89678"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("queued_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("scrape_rules", sa.JSON(), nullable=True),
        sa.Column(
            "error_message",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scrape_runs_campaign_id"), "scrape_runs", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_scrape_runs_status"), "scrape_runs", ["status"], unique=False)

    op.create_table(
        "scrape_run_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("scrape_job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "error_code",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["scrape_runs.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["scrape_job_id"], ["scrapejob.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scrape_run_items_run_id"), "scrape_run_items", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_scrape_run_items_company_id"), "scrape_run_items", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_scrape_run_items_scrape_job_id"),
        "scrape_run_items",
        ["scrape_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_scrape_run_items_status"), "scrape_run_items", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scrape_run_items_status"), table_name="scrape_run_items")
    op.drop_index(op.f("ix_scrape_run_items_scrape_job_id"), table_name="scrape_run_items")
    op.drop_index(op.f("ix_scrape_run_items_company_id"), table_name="scrape_run_items")
    op.drop_index(op.f("ix_scrape_run_items_run_id"), table_name="scrape_run_items")
    op.drop_table("scrape_run_items")
    op.drop_index(op.f("ix_scrape_runs_status"), table_name="scrape_runs")
    op.drop_index(op.f("ix_scrape_runs_campaign_id"), table_name="scrape_runs")
    op.drop_table("scrape_runs")
