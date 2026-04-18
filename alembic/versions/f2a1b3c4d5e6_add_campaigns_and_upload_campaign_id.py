"""add campaigns and upload campaign_id

Revision ID: f2a1b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-04-18

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a1b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_campaigns_id"), "campaigns", ["id"], unique=False)
    op.create_index(op.f("ix_campaigns_name"), "campaigns", ["name"], unique=False)
    op.create_index(op.f("ix_campaigns_created_at"), "campaigns", ["created_at"], unique=False)
    op.create_index(op.f("ix_campaigns_updated_at"), "campaigns", ["updated_at"], unique=False)

    op.add_column("uploads", sa.Column("campaign_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_uploads_campaign_id"), "uploads", ["campaign_id"], unique=False)
    op.create_foreign_key(
        "fk_uploads_campaign_id_campaigns",
        "uploads",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_uploads_campaign_id_campaigns", "uploads", type_="foreignkey")
    op.drop_index(op.f("ix_uploads_campaign_id"), table_name="uploads")
    op.drop_column("uploads", "campaign_id")

    op.drop_index(op.f("ix_campaigns_updated_at"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_created_at"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_name"), table_name="campaigns")
    op.drop_index(op.f("ix_campaigns_id"), table_name="campaigns")
    op.drop_table("campaigns")
