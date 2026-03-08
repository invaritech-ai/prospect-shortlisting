"""add unique constraint on active scrapejob url

Revision ID: a1b2c3d4e5f6
Revises: e6f511e2f9d8
Create Date: 2026-03-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e6f511e2f9d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial unique index: only one active (non-terminal) job per normalized_url.
    # Historical completed/failed jobs are not constrained.
    op.create_index(
        "uq_scrapejob_active_normalized_url",
        "scrapejob",
        ["normalized_url"],
        unique=True,
        postgresql_where=sa.text("terminal_state = false"),
        sqlite_where=sa.text("terminal_state = 0"),
    )


def downgrade() -> None:
    op.drop_index("uq_scrapejob_active_normalized_url", table_name="scrapejob")
