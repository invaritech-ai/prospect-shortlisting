"""Procrastinate application singleton.

Owns the Procrastinate App and its psycopg2 connector. Imported by:
- the worker process (`procrastinate worker`) to discover task definitions
- API request handlers that defer jobs (e.g. via `task.defer_async()`)
- the smoke ping endpoint
"""
from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.core.config import settings


# PsycopgConnector expects a plain psycopg DSN (postgresql://...).
# SQLAlchemy uses a dialect prefix (postgresql+psycopg://...) that psycopg rejects.
_psycopg_dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

_connector = PsycopgConnector(
    conninfo=_psycopg_dsn,
    min_size=1,   # one warm connection; avoids fully cold starts on worker boot
    max_size=4,   # concurrency + headroom; tune up if worker -c > 3
    timeout=60,   # remote DB takes ~3 s per connection; 30 s default is too tight
    # kwargs is a named pool param (not **kwargs); defaults to None which causes
    # **pool.kwargs to crash in listen_notify. Pass explicit connection-level args.
    kwargs={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    },
)

app = App(
    connector=_connector,
    import_paths=[
        "app.jobs.health",
        "app.jobs.scrape",
        "app.jobs.ai_decision",
        "app.jobs.contact_fetch",
        "app.jobs.email_reveal",
        "app.jobs.validation",
    ],
)
