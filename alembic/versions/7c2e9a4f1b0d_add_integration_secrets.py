"""add integration_secrets table for encrypted API keys

Revision ID: 7c2e9a4f1b0d
Revises: 5183c46ce6e8
Create Date: 2026-04-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "7c2e9a4f1b0d"
down_revision: Union[str, Sequence[str], None] = "5183c46ce6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_secrets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("last4", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "field_name", name="uq_integration_secrets_provider_field"),
    )
    op.create_index(op.f("ix_integration_secrets_id"), "integration_secrets", ["id"], unique=False)
    op.create_index(op.f("ix_integration_secrets_provider"), "integration_secrets", ["provider"], unique=False)
    op.create_index(op.f("ix_integration_secrets_field_name"), "integration_secrets", ["field_name"], unique=False)
    op.create_index(op.f("ix_integration_secrets_created_at"), "integration_secrets", ["created_at"], unique=False)
    op.create_index(op.f("ix_integration_secrets_updated_at"), "integration_secrets", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_secrets_updated_at"), table_name="integration_secrets")
    op.drop_index(op.f("ix_integration_secrets_created_at"), table_name="integration_secrets")
    op.drop_index(op.f("ix_integration_secrets_field_name"), table_name="integration_secrets")
    op.drop_index(op.f("ix_integration_secrets_provider"), table_name="integration_secrets")
    op.drop_index(op.f("ix_integration_secrets_id"), table_name="integration_secrets")
    op.drop_table("integration_secrets")
