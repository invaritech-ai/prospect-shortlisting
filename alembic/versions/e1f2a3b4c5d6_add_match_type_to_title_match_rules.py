"""add match_type to title_match_rules

Revision ID: e1f2a3b4c5d6
Revises: c9d8e7f6a5b4
Create Date: 2026-04-16

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "c9d8e7f6a5b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "title_match_rules",
        sa.Column("match_type", sa.String(length=32), nullable=False, server_default="keyword"),
    )


def downgrade() -> None:
    op.drop_column("title_match_rules", "match_type")
