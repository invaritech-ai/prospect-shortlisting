"""add llm rate limits

Revision ID: a6b7c8d9e0f1
Revises: 4d7a2c9f1b64
Create Date: 2026-05-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "4d7a2c9f1b64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_rate_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False),
        sa.Column("min_gap_ms", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False),
        sa.Column("last_request_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "purpose", name="uq_llm_rate_limits_provider_purpose"),
    )
    op.create_index(op.f("ix_llm_rate_limits_id"), "llm_rate_limits", ["id"], unique=False)
    op.create_index(op.f("ix_llm_rate_limits_provider"), "llm_rate_limits", ["provider"], unique=False)
    op.create_index(op.f("ix_llm_rate_limits_purpose"), "llm_rate_limits", ["purpose"], unique=False)
    op.create_index(op.f("ix_llm_rate_limits_window_started_at"), "llm_rate_limits", ["window_started_at"], unique=False)
    op.create_index(op.f("ix_llm_rate_limits_created_at"), "llm_rate_limits", ["created_at"], unique=False)
    op.execute(
        """
        INSERT INTO llm_rate_limits (
            id, provider, purpose, requests_per_minute, min_gap_ms,
            window_started_at, requests_used, last_request_at, created_at, updated_at
        )
        VALUES (
            '11111111-1111-1111-1111-111111111111', 'openrouter', 'ai_decision', 12, 5000,
            now(), 0, NULL, now(), now()
        )
        ON CONFLICT (provider, purpose) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM llm_rate_limits WHERE provider = 'openrouter' AND purpose = 'ai_decision'")
    op.drop_index(op.f("ix_llm_rate_limits_created_at"), table_name="llm_rate_limits")
    op.drop_index(op.f("ix_llm_rate_limits_window_started_at"), table_name="llm_rate_limits")
    op.drop_index(op.f("ix_llm_rate_limits_purpose"), table_name="llm_rate_limits")
    op.drop_index(op.f("ix_llm_rate_limits_provider"), table_name="llm_rate_limits")
    op.drop_index(op.f("ix_llm_rate_limits_id"), table_name="llm_rate_limits")
    op.drop_table("llm_rate_limits")
