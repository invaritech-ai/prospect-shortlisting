"""Procrastinate application singleton.

Owns the Procrastinate App and its psycopg2 connector. Imported by:
- the worker process (`procrastinate worker`) to discover task definitions
- API request handlers that defer jobs (e.g. via `task.defer_async()`)
- the smoke ping endpoint
"""
from __future__ import annotations

import os

from procrastinate import App, PsycopgConnector

from app.core.config import settings
from app.core.logging import configure_logging


# Procrastinate workers don't go through app/main.py, so the FastAPI startup
# hook never runs and the root logger stays at WARNING — every `logger.info`
# from worker-side code (e.g. the [discover] traces) is silently dropped.
# Configure logging at module import so any process that imports the queue app
# (worker, API, scripts) gets INFO-level logs.
configure_logging()


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

# Keep the default boot path minimal so stage-specific workers can start even
# while other pipeline modules are being refactored.
_DEFAULT_IMPORT_PATHS = [
    "app.jobs.health",
    "app.jobs.scrape",
    "app.jobs.ai_decision",
]

# Optional override for full task registration when all modules are healthy.
# Example:
#   PS_PROCRASTINATE_IMPORT_PATHS=app.jobs.health,app.jobs.scrape,app.jobs.ai_decision,...
_import_paths_env = os.environ.get("PS_PROCRASTINATE_IMPORT_PATHS", "").strip()
_import_paths = (
    [p.strip() for p in _import_paths_env.split(",") if p.strip()]
    if _import_paths_env
    else _DEFAULT_IMPORT_PATHS
)

app = App(
    connector=_connector,
    import_paths=_import_paths,
)
