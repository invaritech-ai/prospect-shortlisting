"""Procrastinate application singleton.

Owns the Procrastinate App and its psycopg2 connector. Imported by:
- the worker process (`procrastinate worker`) to discover task definitions
- API request handlers that defer jobs (e.g. via `task.defer_async()`)
- the smoke ping endpoint
"""
from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.core.config import settings


_connector = PsycopgConnector(conninfo=settings.database_url)

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
