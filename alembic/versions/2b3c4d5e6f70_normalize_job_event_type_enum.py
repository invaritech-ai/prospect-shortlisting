"""normalize job event type enum

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2b3c4d5e6f70"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def _enum_value_exists(enum_name: str, value: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = :enum_name
                  AND e.enumlabel = :value
                """
            ),
            {"enum_name": enum_name, "value": value},
        ).first()
    )


def _rename_enum_value(enum_name: str, old: str, new: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if _enum_value_exists(enum_name, old) and not _enum_value_exists(enum_name, new):
        op.execute(f"ALTER TYPE {enum_name} RENAME VALUE '{old}' TO '{new}'")


def _add_enum_value(enum_name: str, value: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _enum_value_exists(enum_name, value):
        op.execute(f"ALTER TYPE {enum_name} ADD VALUE '{value}'")


def upgrade() -> None:
    _rename_enum_value("jobtype", "CRAWL", "crawl")
    _rename_enum_value("jobtype", "ANALYSIS", "analysis")
    _add_enum_value("jobtype", "contact_fetch")


def downgrade() -> None:
    _rename_enum_value("jobtype", "analysis", "ANALYSIS")
    _rename_enum_value("jobtype", "crawl", "CRAWL")
