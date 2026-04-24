"""align contact_fetch_jobs provider index with live schema

Revision ID: d1e2f3a4b5c6
Revises: a5b6c7d8e9f0
Create Date: 2026-04-24

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return _table_exists(inspector, table_name) and any(
        index["name"] == index_name for index in inspector.get_indexes(table_name)
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if _index_exists(inspector, "contact_fetch_jobs", "uq_contact_fetch_jobs_company_active"):
        op.drop_index("uq_contact_fetch_jobs_company_active", table_name="contact_fetch_jobs")

    if not _index_exists(inspector, "contact_fetch_jobs", op.f("ix_contact_fetch_jobs_provider")):
        op.create_index(op.f("ix_contact_fetch_jobs_provider"), "contact_fetch_jobs", ["provider"], unique=False)


def downgrade() -> None:
    """Schema repair migrations are forward-only."""
    pass
