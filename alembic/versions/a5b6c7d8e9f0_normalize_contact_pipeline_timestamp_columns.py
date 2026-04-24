"""normalize contact pipeline timestamp columns to naive UTC timestamps

Revision ID: a5b6c7d8e9f0
Revises: f4e5d6c7b8a9
Create Date: 2026-04-24

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f4e5d6c7b8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TIMESTAMP_COLUMNS_TO_NORMALIZE: dict[str, tuple[str, ...]] = {
    "contact_fetch_batches": ("created_at", "finished_at", "updated_at"),
    "contact_fetch_runtime_controls": ("created_at", "updated_at"),
    "contact_provider_attempts": (
        "created_at",
        "finished_at",
        "lock_expires_at",
        "next_retry_at",
        "started_at",
        "updated_at",
    ),
    "contact_reveal_batches": ("created_at", "finished_at", "updated_at"),
    "contact_reveal_jobs": ("created_at", "finished_at", "lock_expires_at", "started_at", "updated_at"),
    "contact_reveal_attempts": (
        "created_at",
        "finished_at",
        "lock_expires_at",
        "next_retry_at",
        "started_at",
        "updated_at",
    ),
    "discovered_contacts": ("created_at", "discovered_at", "last_seen_at", "updated_at"),
}


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_info(inspector: sa.Inspector, table_name: str, column_name: str) -> dict[str, object] | None:
    if not _table_exists(inspector, table_name):
        return None
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return column
    return None


def _normalize_timestamp_column(inspector: sa.Inspector, table_name: str, column_name: str) -> None:
    column = _column_info(inspector, table_name, column_name)
    if column is None:
        return

    column_type = column["type"]
    if not getattr(column_type, "timezone", False):
        return

    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, column_names in TIMESTAMP_COLUMNS_TO_NORMALIZE.items():
        for column_name in column_names:
            _normalize_timestamp_column(inspector, table_name, column_name)


def downgrade() -> None:
    """Schema repair migrations are forward-only."""
    pass
