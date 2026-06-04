"""verification_batch_notify_trigger

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-06-04
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "a8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION notify_verification_batch_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
  payload TEXT;
BEGIN
  payload := json_build_object(
    'job_type',       'verification_batch',
    'job_id',         NEW.id,
    'batch_id',       NEW.id,
    'campaign_id',    NEW.campaign_id,
    'state',          NEW.state,
    'selected_count', NEW.selected_count,
    'queued_count',   NEW.queued_count,
    'verified_count', NEW.verified_count,
    'valid_count',    NEW.valid_count,
    'invalid_count',  NEW.invalid_count,
    'skipped_count',  NEW.skipped_count,
    'finished_at',    NEW.finished_at
  )::text;
  PERFORM pg_notify('job_events', payload);
  RETURN NEW;
END;
$$;

CREATE TRIGGER verification_batches_notify
AFTER INSERT OR UPDATE ON verification_batches
FOR EACH ROW EXECUTE FUNCTION notify_verification_batch_update();
"""

_DROP_TRIGGER_FN = """
DROP TRIGGER IF EXISTS verification_batches_notify ON verification_batches;
DROP FUNCTION IF EXISTS notify_verification_batch_update();
"""


def upgrade() -> None:
    op.execute(_TRIGGER_FN)


def downgrade() -> None:
    op.execute(_DROP_TRIGGER_FN)
