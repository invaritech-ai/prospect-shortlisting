from __future__ import annotations

from psycopg import errors as pg_errors
from sqlalchemy.exc import DBAPIError

from app.services import queue_guard


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_args, **_kwargs):
        raise DBAPIError(
            statement="SELECT COUNT(*) FROM procrastinate_jobs",
            params={},
            orig=pg_errors.UndefinedTable('relation "procrastinate_jobs" does not exist'),
        )


class _FakeEngine:
    def connect(self):
        return _FakeConn()


def test_available_slots_fail_closed_when_procrastinate_table_missing() -> None:
    engine = _FakeEngine()
    queue = "scrape"

    slots = queue_guard.available_slots(engine=engine, queue=queue, requested=25)  # type: ignore[arg-type]

    assert slots == 0
