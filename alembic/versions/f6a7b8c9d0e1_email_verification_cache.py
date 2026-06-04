"""email verification cache

Revision ID: f6a7b8c9d0e1
Revises: a7b8c9d0e1f2
Create Date: 2026-06-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_verification_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("normalized_email", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sub_status", sa.String(length=64), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_email_verification_cache_id"),
        "email_verification_cache",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_verification_cache_provider"),
        "email_verification_cache",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_verification_cache_normalized_email"),
        "email_verification_cache",
        ["normalized_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_verification_cache_status"),
        "email_verification_cache",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_verification_cache_validated_at"),
        "email_verification_cache",
        ["validated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_verification_cache_created_at"),
        "email_verification_cache",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ux_email_verification_cache_provider_email",
        "email_verification_cache",
        ["provider", "normalized_email"],
        unique=True,
    )
    op.add_column(
        "verification_batches",
        sa.Column("selected_contact_snapshots_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "verification_batches",
        sa.Column("result_summary_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("verification_batches", "result_summary_json")
    op.drop_column("verification_batches", "selected_contact_snapshots_json")
    op.drop_index(
        "ux_email_verification_cache_provider_email",
        table_name="email_verification_cache",
    )
    op.drop_index(
        op.f("ix_email_verification_cache_created_at"),
        table_name="email_verification_cache",
    )
    op.drop_index(
        op.f("ix_email_verification_cache_validated_at"),
        table_name="email_verification_cache",
    )
    op.drop_index(
        op.f("ix_email_verification_cache_status"),
        table_name="email_verification_cache",
    )
    op.drop_index(
        op.f("ix_email_verification_cache_normalized_email"),
        table_name="email_verification_cache",
    )
    op.drop_index(
        op.f("ix_email_verification_cache_provider"),
        table_name="email_verification_cache",
    )
    op.drop_index(
        op.f("ix_email_verification_cache_id"),
        table_name="email_verification_cache",
    )
    op.drop_table("email_verification_cache")
