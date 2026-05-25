"""scrape failure classification

Revision ID: 4d7a2c9f1b64
Revises: ef91a02fa9dd
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d7a2c9f1b64"
down_revision: Union[str, Sequence[str], None] = "ef91a02fa9dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_results", sa.Column("failure_class", sa.String(length=32), nullable=True))
    op.add_column("scrape_results", sa.Column("retryable", sa.Boolean(), nullable=True))
    op.add_column("scrape_results", sa.Column("final_url", sa.String(length=2048), nullable=True))
    op.create_index(op.f("ix_scrape_results_failure_class"), "scrape_results", ["failure_class"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scrape_results_failure_class"), table_name="scrape_results")
    op.drop_column("scrape_results", "final_url")
    op.drop_column("scrape_results", "retryable")
    op.drop_column("scrape_results", "failure_class")
