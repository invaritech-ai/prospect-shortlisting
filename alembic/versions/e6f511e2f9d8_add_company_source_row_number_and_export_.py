"""add company source row number and export ordering support

Revision ID: e6f511e2f9d8
Revises: 9a83ac364758
Create Date: 2026-03-07 23:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f511e2f9d8"
down_revision: Union[str, Sequence[str], None] = "9a83ac364758"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("companies", "raw_url", existing_type=sa.String(length=2048), type_=sa.Text(), existing_nullable=False)
    op.add_column("companies", sa.Column("source_row_number", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_companies_source_row_number"), "companies", ["source_row_number"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_companies_source_row_number"), table_name="companies")
    op.drop_column("companies", "source_row_number")
    op.alter_column("companies", "raw_url", existing_type=sa.Text(), type_=sa.String(length=2048), existing_nullable=False)
