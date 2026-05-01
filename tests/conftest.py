"""Shared fixtures for the test suite."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

# Import all models so SQLModel metadata is populated before create_all.
from app.models import (  # noqa: F401
    AiUsageEvent,
    AnalysisJob,
    ClassificationResult,
    Company,
    CompanyFeedback,
    ContactFetchBatch,
    ContactFetchJob,
    ContactFetchRuntimeControl,
    ContactProviderAttempt,
    ContactRevealAttempt,
    ContactRevealBatch,
    ContactRevealJob,
    ContactVerifyJob,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    PipelineRun,
    PipelineRunEvent,
    Prompt,
    ScrapeJob,
    ScrapePrompt,
    ScrapeRun,
    ScrapeRunItem,
    ScrapePage,
    TitleMatchRule,
    Upload,
)


# ---------------------------------------------------------------------------
# Postgres fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    local_url = os.environ.get("PS_TEST_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if local_url:
        yield local_url
        return

    if os.environ.get("PS_TEST_USE_TESTCONTAINERS") != "1":
        pytest.fail(
            "Postgres tests require PS_TEST_DATABASE_URL or TEST_DATABASE_URL. "
            "Create a dedicated local test database and run, for example: "
            "PS_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/prospect_shortlisting_test "
            "uv run pytest"
        )

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        yield url


@pytest.fixture(scope="session")
def _postgres_engine(postgres_url: str):
    engine = create_engine(postgres_url, echo=False)

    env = {**os.environ, "DATABASE_URL": postgres_url, "PS_DATABASE_URL": postgres_url}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )

    yield engine
    engine.dispose()


def _truncate_all(engine) -> None:
    with engine.begin() as connection:
        tables = list(
            connection.exec_driver_sql(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename != 'alembic_version'
                """
            ).scalars()
        )
        if tables:
            preparer = engine.dialect.identifier_preparer
            table_list = ", ".join(preparer.quote(t) for t in tables)
            connection.exec_driver_sql(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")


@pytest.fixture(autouse=True)
def _clean_db(_postgres_engine) -> Generator[None, None, None]:
    """Truncate all tables before each test for full isolation."""
    _truncate_all(_postgres_engine)
    yield


@pytest.fixture
def db_engine(_postgres_engine):
    """Yield the Postgres engine for service-level tests."""
    return _postgres_engine


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    """Yield a Postgres session backed by the real engine."""
    with Session(db_engine) as sess:
        yield sess


@pytest.fixture
def session(db_session: Session) -> Generator[Session, None, None]:
    """Compatibility alias for tests that use the generic session fixture."""
    yield db_session
