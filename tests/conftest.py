"""Shared fixtures for the test suite."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Generator

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Import all models so SQLModel metadata is populated before create_all.
from app.models import (  # noqa: F401
    AnalysisJob,
    ClassificationResult,
    Company,
    CompanyFeedback,
    ContactFetchJob,
    ContactVerifyJob,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    Prompt,
    ProspectContact,
    Run,
    ScrapeJob,
    ScrapePage,
    TitleMatchRule,
    Upload,
)


# ---------------------------------------------------------------------------
# Lightweight SQLite fixtures — no containers needed, fast
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sqlite_engine():
    """In-memory SQLite engine with all tables created from SQLModel metadata."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sqlite_session(sqlite_engine) -> Generator[Session, None, None]:
    """Yield a plain session; each test manages its own commits (SQLite in-memory)."""
    with Session(sqlite_engine) as sess:
        yield sess


# ---------------------------------------------------------------------------
# Full Postgres fixtures — requires Docker, used for integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        yield url


@pytest.fixture(scope="session")
def db_engine(postgres_url: str):
    engine = create_engine(postgres_url, echo=False)

    env = {**os.environ, "DATABASE_URL": postgres_url}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        cwd=str(__import__("pathlib").Path(__file__).parent.parent),
    )

    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine) -> Generator[Session, None, None]:
    """Yield a session that rolls back after each test (Postgres)."""
    connection = db_engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()
