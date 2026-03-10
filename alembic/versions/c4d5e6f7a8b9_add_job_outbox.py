"""add job_outbox table for transactional outbox pattern

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-11 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("task_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stream_id", sa.String(length=128), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Fast dispatcher scan: pending rows ordered by age
    op.create_index(
        "ix_job_outbox_pending",
        "job_outbox",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    # Idempotency guard: one pending entry per (job_id, task_type)
    # NOTE: op.create_unique_constraint does NOT support postgresql_where;
    # a unique partial index achieves the same constraint.
    op.create_index(
        "uq_job_outbox_pending",
        "job_outbox",
        ["job_id", "task_type"],
        unique=True,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_job_outbox_pending", table_name="job_outbox")
    op.drop_index("ix_job_outbox_pending", table_name="job_outbox")
    op.drop_table("job_outbox")
