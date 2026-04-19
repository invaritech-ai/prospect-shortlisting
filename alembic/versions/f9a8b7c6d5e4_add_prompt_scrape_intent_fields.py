"""add prompt scrape intent + derived rules fields

Revision ID: f9a8b7c6d5e4
Revises: f2a1b3c4d5e6
Create Date: 2026-04-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f9a8b7c6d5e4"
down_revision: Union[str, Sequence[str], None] = "f2a1b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("scrape_pages_intent_text", sa.Text(), nullable=True))
    op.add_column("prompts", sa.Column("scrape_rules_structured", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("prompts", "scrape_rules_structured")
    op.drop_column("prompts", "scrape_pages_intent_text")
