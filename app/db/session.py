from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.models import (  # noqa: F401
    AnalysisJob,
    Campaign,
    ClassificationResult,
    Company,
    CompanyFeedback,
    ContactFetchJob,
    ContactVerifyJob,
    CrawlArtifact,
    CrawlJob,
    IntegrationSecret,
    JobEvent,
    Prompt,
    ProspectContact,
    ProspectContactEmail,
    Run,
    ScrapeJob,
    ScrapePage,
    TitleMatchRule,
    Upload,
)


_is_sqlite = settings.database_url.startswith("sqlite")
# Celery workers are serial (prefetch_multiplier=1) — they only ever run one
# task at a time, so a persistent pool wastes connections. NullPool opens a
# fresh connection per Session and closes it immediately on exit, keeping the
# total connection count at 1-2 per worker instead of pool_size (20).
_is_worker = os.environ.get("PS_WORKER_PROCESS") == "1"

if _is_sqlite:
    connect_args: dict = {"check_same_thread": False}
    _pool_kwargs: dict = {}
elif _is_worker:
    connect_args = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    _pool_kwargs = {"poolclass": NullPool}
else:
    connect_args = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    # API: 5 connections steady-state, burst to 10. Leaves room for workers.
    _pool_kwargs = {"pool_size": 5, "max_overflow": 5, "pool_recycle": 300}

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args,
    **_pool_kwargs,
)


def get_engine():  # type: ignore[return]
    return engine


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
