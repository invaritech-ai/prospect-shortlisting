"""add contact provider and apollo raw payload

Revision ID: 7f8e9d0c1b2a
Revises: d4e5f6a7b8c9
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f8e9d0c1b2a"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "contact_fetch_jobs",
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
            server_default=sa.text("'snov'"),
        ),
    )
    op.add_column("prospect_contacts", sa.Column("apollo_prospect_raw", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("prospect_contacts", "apollo_prospect_raw")
    op.drop_column("contact_fetch_jobs", "provider")
