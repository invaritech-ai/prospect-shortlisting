"""add_manual_label_to_company_feedback

Revision ID: b5c6d7e8f9a0
Revises: 1a2c4859f996
Create Date: 2026-03-20 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "1a2c4859f996"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_feedback",
        sa.Column("manual_label", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_feedback", "manual_label")
