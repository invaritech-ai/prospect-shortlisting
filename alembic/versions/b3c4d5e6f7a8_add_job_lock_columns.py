"""add lock_token and lock_expires_at for job ownership

Revision ID: b3c4d5e6f7a8
Revises: f7e8d9c0b1a2
Create Date: 2026-03-10 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "f7e8d9c0b1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrapejob", sa.Column("lock_token", sa.String(length=64), nullable=True))
    op.add_column("scrapejob", sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analysis_jobs", sa.Column("lock_token", sa.String(length=64), nullable=True))
    op.add_column("analysis_jobs", sa.Column("lock_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_jobs", "lock_expires_at")
    op.drop_column("analysis_jobs", "lock_token")
    op.drop_column("scrapejob", "lock_expires_at")
    op.drop_column("scrapejob", "lock_token")
