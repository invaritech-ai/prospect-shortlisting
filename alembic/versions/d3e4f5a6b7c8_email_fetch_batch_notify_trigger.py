"""email_fetch_batch_notify_trigger

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION notify_email_fetch_batch_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
  payload TEXT;
BEGIN
  payload := json_build_object(
    'job_type',              'email_fetch_batch',
    'job_id',                NEW.id,
    'batch_id',              NEW.id,
    'campaign_id',           NEW.campaign_id,
    'state',                 NEW.state,
    'selected_domain_count', NEW.selected_domain_count,
    'success_count',         NEW.success_count,
    'failed_count',          NEW.failed_count,
    'queued_count',          NEW.queued_count,
    'finished_at',           NEW.finished_at
  )::text;
  PERFORM pg_notify('job_events', payload);
  RETURN NEW;
END;
$$;

CREATE TRIGGER email_fetch_batches_notify
AFTER INSERT OR UPDATE ON email_fetch_batches
FOR EACH ROW EXECUTE FUNCTION notify_email_fetch_batch_update();
"""

_DROP_TRIGGER_FN = """
DROP TRIGGER IF EXISTS email_fetch_batches_notify ON email_fetch_batches;
DROP FUNCTION IF EXISTS notify_email_fetch_batch_update();
"""


def upgrade() -> None:
    op.execute(_TRIGGER_FN)


def downgrade() -> None:
    op.execute(_DROP_TRIGGER_FN)
