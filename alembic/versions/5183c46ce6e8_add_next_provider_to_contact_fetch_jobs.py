"""add next_provider to contact_fetch_jobs

Revision ID: 5183c46ce6e8
Revises: e8f9a0b1c2d3
Create Date: 2026-04-20 22:53:36.960753

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5183c46ce6e8'
down_revision: Union[str, Sequence[str], None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "contact_fetch_jobs",
        sa.Column("next_provider", sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f("ix_contact_fetch_jobs_next_provider"),
        "contact_fetch_jobs",
        ["next_provider"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_contact_fetch_jobs_next_provider"), table_name="contact_fetch_jobs")
    op.drop_column("contact_fetch_jobs", "next_provider")
