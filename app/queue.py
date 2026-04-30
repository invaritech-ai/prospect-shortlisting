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
    min_size=0,
    max_size=10,
    kwargs={},  # psycopg_pool.AsyncConnectionPool.kwargs defaults to None;
                # Procrastinate does **pool.kwargs in listen_notify which crashes on None
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
