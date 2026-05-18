"""scrape_batch_notify_trigger

Revision ID: ef91a02fa9dd
Revises: 62b35fbbba2e
Create Date: 2026-05-19 00:50:26.789535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef91a02fa9dd'
down_revision: Union[str, Sequence[str], None] = '62b35fbbba2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION notify_scrape_batch_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
  payload TEXT;
BEGIN
  payload := json_build_object(
    'job_type',              'scrape_batch',
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

CREATE TRIGGER scrape_batches_notify
AFTER INSERT OR UPDATE ON scrape_batches
FOR EACH ROW EXECUTE FUNCTION notify_scrape_batch_update();
"""

_DROP_TRIGGER_FN = """
DROP TRIGGER IF EXISTS scrape_batches_notify ON scrape_batches;
DROP FUNCTION IF EXISTS notify_scrape_batch_update();
"""


def upgrade() -> None:
    op.execute(_TRIGGER_FN)


def downgrade() -> None:
    op.execute(_DROP_TRIGGER_FN)
