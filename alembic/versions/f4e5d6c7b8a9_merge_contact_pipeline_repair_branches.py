"""merge contact pipeline repair branches

Revision ID: f4e5d6c7b8a9
Revises: 9c2d3e4f5a6b, dc4662e17bfb
Create Date: 2026-04-24

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "f4e5d6c7b8a9"
down_revision: Union[str, Sequence[str], None] = ("9c2d3e4f5a6b", "dc4662e17bfb")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
