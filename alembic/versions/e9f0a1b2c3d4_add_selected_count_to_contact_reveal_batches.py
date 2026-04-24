"""Add selected_count to contact_reveal_batches.

Revision ID: e9f0a1b2c3d4
Revises: d1e2f3a4b5c6
Create Date: 2026-04-24 00:00:00.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "e9f0a1b2c3d4"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def _json_list_length(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return 0
        return len(parsed) if isinstance(parsed, list) else 0
    try:
        return len(value)  # type: ignore[arg-type]
    except TypeError:
        return 0


def upgrade() -> None:
    op.add_column(
        "contact_reveal_batches",
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
    )

    conn = op.get_bind()
    batch_rows = list(
        conn.execute(
            sa.text("SELECT id, requested_count FROM contact_reveal_batches")
        ).mappings()
    )
    for batch_row in batch_rows:
        job_rows = list(
            conn.execute(
                sa.text(
                    "SELECT discovered_contact_ids_json "
                    "FROM contact_reveal_jobs "
                    "WHERE contact_reveal_batch_id = :batch_id"
                ),
                {"batch_id": batch_row["id"]},
            )
        )
        selected_count = sum(_json_list_length(row[0]) for row in job_rows)
        if selected_count == 0:
            selected_count = int(batch_row["requested_count"] or 0)
        conn.execute(
            sa.text(
                "UPDATE contact_reveal_batches "
                "SET selected_count = :selected_count "
                "WHERE id = :batch_id"
            ),
            {"selected_count": int(selected_count), "batch_id": batch_row["id"]},
        )

    op.alter_column("contact_reveal_batches", "selected_count", server_default=None)


def downgrade() -> None:
    op.drop_column("contact_reveal_batches", "selected_count")
