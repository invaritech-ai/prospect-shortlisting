"""add pg_notify trigger on job_events for SSE fan-out

Adds an AFTER INSERT trigger that emits a NOTIFY on channel `job_events`
with a small JSON payload. This is purely additive — no application code
writes through the trigger, and `JobEvent` writers are unchanged. If the
listener (API process) is down, NOTIFYs are dropped silently; the existing
DB rows remain authoritative.

Revision ID: a1c2e3f4d5b6
Revises: e510191a58fc
Create Date: 2026-05-08
"""
from __future__ import annotations

from alembic import op

revision = "a1c2e3f4d5b6"
down_revision = "e510191a58fc"
branch_labels = None
depends_on = None


_FN = "job_events_notify"
_TRIGGER = "job_events_notify_trg"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FN}() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'job_events',
                json_build_object(
                    'id', NEW.id,
                    'job_type', NEW.job_type,
                    'job_id', NEW.job_id,
                    'from_state', NEW.from_state,
                    'to_state', NEW.to_state,
                    'event_type', NEW.event_type,
                    'created_at', to_char(NEW.created_at AT TIME ZONE 'UTC',
                                          'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON job_events;")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
        AFTER INSERT ON job_events
        FOR EACH ROW EXECUTE FUNCTION {_FN}();
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON job_events;")
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}();")
