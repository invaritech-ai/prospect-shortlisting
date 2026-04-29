"""backfill unknown failure reasons

Revision ID: 1a2b3c4d5e6f
Revises: 0f1e2d3c4b5a
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op


revision = "1a2b3c4d5e6f"
down_revision = "0f1e2d3c4b5a"
branch_labels = None
depends_on = None


TABLES = (
    "scrapejob",
    "crawl_jobs",
    "contact_fetch_jobs",
    "contact_provider_attempts",
    "contact_reveal_attempts",
)


def upgrade() -> None:
    for table_name in TABLES:
        op.execute(
            f"""
            UPDATE {table_name}
            SET failure_reason = 'unknown'
            WHERE state IN ('failed', 'dead')
              AND failure_reason IS NULL
            """
        )


def downgrade() -> None:
    for table_name in TABLES:
        op.execute(
            f"""
            UPDATE {table_name}
            SET failure_reason = NULL
            WHERE failure_reason = 'unknown'
            """
        )
