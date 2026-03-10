"""Shared fixtures: real Postgres + Redis containers, one per test session."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Generator

import pytest
from redis import Redis
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

# Import all models so SQLModel metadata is populated before create_all.
from app.models import (  # noqa: F401
    AnalysisJob,
    ClassificationResult,
    Company,
    CompanyFeedback,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    JobOutbox,
    Prompt,
    Run,
    ScrapeJob,
    Upload,
)
from app.models.scrape import ScrapePage  # noqa: F401


# ---------------------------------------------------------------------------
# Container fixtures — one pair per test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        # psycopg3 requires postgresql+psycopg:// scheme
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
        yield url


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:
    return redis_container.get_connection_url()


@pytest.fixture(scope="session")
def redis_container():
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        yield r


# ---------------------------------------------------------------------------
# DB engine + schema
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_engine(postgres_url: str):
    engine = create_engine(postgres_url, echo=False)

    # Run Alembic migrations (real migrations, not SQLModel.metadata.create_all).
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
    """Yield a session that rolls back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# Redis client
# ---------------------------------------------------------------------------


@pytest.fixture
def redis_client(redis_container) -> Generator[Redis, None, None]:
    client = Redis.from_url(redis_container.get_connection_url(), decode_responses=True)
    yield client
    # Clean up stream and group after each test.
    try:
        client.delete("jobs:stream")
    except Exception:  # noqa: BLE001
        pass
    client.close()
