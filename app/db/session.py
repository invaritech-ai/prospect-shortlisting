from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.models import (  # noqa: F401
    AnalysisJob,
    ClassificationResult,
    Company,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    Prompt,
    Run,
    ScrapeJob,
    ScrapePage,
    Upload,
)


_is_sqlite = settings.database_url.startswith("sqlite")
if _is_sqlite:
    connect_args: dict = {"check_same_thread": False}
else:
    connect_args = {
        "connect_timeout": 10,      # fail fast if host is unreachable (seconds)
        "keepalives": 1,            # enable TCP keepalives
        "keepalives_idle": 30,      # start probing after 30s of silence
        "keepalives_interval": 10,  # retry every 10s
        "keepalives_count": 3,      # drop after 3 failed probes
    }
_pool_kwargs = {} if _is_sqlite else {"pool_size": 20, "max_overflow": 5}
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
