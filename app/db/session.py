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


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
_is_sqlite = settings.database_url.startswith("sqlite")
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
