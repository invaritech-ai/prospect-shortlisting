"""Add is_stale to classification_results.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-02

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "classification_results",
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_classification_results_is_stale",
        "classification_results",
        ["is_stale"],
    )


def downgrade() -> None:
    op.drop_index("ix_classification_results_is_stale", table_name="classification_results")
    op.drop_column("classification_results", "is_stale")
