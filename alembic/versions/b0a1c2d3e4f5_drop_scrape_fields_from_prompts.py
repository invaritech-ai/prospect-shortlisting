"""drop scrape-specific fields from S2 prompts

Revision ID: b0a1c2d3e4f5
Revises: a9b8c7d6e5f4
Create Date: 2026-04-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b0a1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("prompts", "scrape_rules_structured")
    op.drop_column("prompts", "scrape_pages_intent_text")


def downgrade() -> None:
    op.add_column("prompts", sa.Column("scrape_pages_intent_text", sa.Text(), nullable=True))
    op.add_column("prompts", sa.Column("scrape_rules_structured", sa.JSON(), nullable=True))
