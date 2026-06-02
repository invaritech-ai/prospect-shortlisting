"""email fetch batch metadata

Revision ID: b1c2d3e4f5a6
Revises: a6b7c8d9e0f1
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_fetch_batches", sa.Column("selected_domain_ids_json", sa.JSON(), nullable=True))
    op.add_column("email_fetch_batches", sa.Column("result_summary_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("email_fetch_batches", "result_summary_json")
    op.drop_column("email_fetch_batches", "selected_domain_ids_json")
