"""Add input_hash and from_cache to classification_results.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-27

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "classification_results",
        sa.Column("input_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "classification_results",
        sa.Column("from_cache", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_classification_results_input_hash",
        "classification_results",
        ["input_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_classification_results_input_hash", table_name="classification_results")
    op.drop_column("classification_results", "from_cache")
    op.drop_column("classification_results", "input_hash")
