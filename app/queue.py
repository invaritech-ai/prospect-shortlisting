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

_worker_concurrency_env = os.environ.get("PS_WORKER_CONCURRENCY", "").strip()
try:
    _worker_concurrency = max(1, int(_worker_concurrency_env)) if _worker_concurrency_env else 1
except ValueError:
    _worker_concurrency = 1
_pool_min_size = max(1, settings.procrastinate_pool_min_size)
_pool_max_default = max(_pool_min_size, _worker_concurrency + 2)
_pool_max_size_env = os.environ.get("PS_PROCRASTINATE_POOL_MAX_SIZE", "").strip()
try:
    _pool_max_size_override = max(1, int(_pool_max_size_env)) if _pool_max_size_env else None
except ValueError:
    _pool_max_size_override = None
_pool_max_size = max(
    _pool_min_size,
    settings.procrastinate_pool_max_size,
    _pool_max_default,
    _pool_max_size_override or 0,
)

_connector = PsycopgConnector(
    conninfo=_psycopg_dsn,
    min_size=_pool_min_size,
    max_size=_pool_max_size,
    timeout=settings.procrastinate_pool_timeout_sec,
    # kwargs is a named pool param (not **kwargs); defaults to None which causes
    # **pool.kwargs to crash in listen_notify. Pass explicit connection-level args.
    kwargs={
        "connect_timeout": settings.db_connect_timeout_sec,
        "keepalives": settings.db_keepalives,
        "keepalives_idle": settings.db_keepalives_idle_sec,
        "keepalives_interval": settings.db_keepalives_interval_sec,
        "keepalives_count": settings.db_keepalives_count,
    },
)

# Keep the default boot path minimal so stage-specific workers can start even
# while other pipeline modules are being refactored.
_DEFAULT_IMPORT_PATHS = [
    "app.jobs.health",
    "app.jobs.scrape",
    "app.jobs.ai_decision",
    "app.jobs.email_fetch",
    "app.jobs.validation",
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
