"""add composite index (campaign_id, created_at) on ai_usage_events

Revision ID: e510191a58fc
Revises: 4f6a7b8c9d0e
Create Date: 2026-05-07

The cost-stats endpoint filters every query by `campaign_id` AND
`created_at >= window_cutoff`. The existing single-column indexes force
Postgres into a bitmap-AND of two index scans for that pattern; a
composite index on (campaign_id, created_at) lets the planner do a
single sorted range scan, which is materially faster on a year-long
window once the table grows.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e510191a58fc"
down_revision = "4f6a7b8c9d0e"
branch_labels = None
depends_on = None


_INDEX_NAME = "ix_ai_usage_events_campaign_created"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("ai_usage_events")}
    if _INDEX_NAME not in indexes:
        op.create_index(
            _INDEX_NAME,
            "ai_usage_events",
            ["campaign_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("ai_usage_events")}
    if _INDEX_NAME in indexes:
        op.drop_index(_INDEX_NAME, table_name="ai_usage_events")
