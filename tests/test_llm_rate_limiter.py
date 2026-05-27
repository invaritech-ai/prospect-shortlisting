from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import SQLModel, Session, create_engine, select

import app.models.llm_rate_limit  # noqa: F401
from app.models.llm_rate_limit import LlmRateLimit
from app.services.llm_rate_limiter import acquire_llm_slot


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_rate_limiter_creates_default_bucket_and_allows_first_slot() -> None:
    with _session() as session:
        out = acquire_llm_slot(session=session, provider="openrouter", purpose="ai_decision")
        row = session.exec(select(LlmRateLimit)).one()

    assert out.allowed is True
    assert out.retry_after_ms == 0
    assert row.provider == "openrouter"
    assert row.purpose == "ai_decision"
    assert row.requests_per_minute == 12
    assert row.min_gap_ms == 5000
    assert row.requests_used == 1


def test_rate_limiter_returns_retry_after_when_min_gap_not_met() -> None:
    now = datetime.now(timezone.utc)
    with _session() as session:
        session.add(
            LlmRateLimit(
                provider="openrouter",
                purpose="ai_decision",
                requests_per_minute=12,
                min_gap_ms=5000,
                window_started_at=now,
                requests_used=1,
                last_request_at=now,
            )
        )
        session.commit()

        out = acquire_llm_slot(
            session=session,
            provider="openrouter",
            purpose="ai_decision",
            now=now + timedelta(seconds=1),
        )

    assert out.allowed is False
    assert 3900 <= out.retry_after_ms <= 4100


def test_rate_limiter_resets_expired_minute_window() -> None:
    old = datetime.now(timezone.utc) - timedelta(seconds=70)
    now = datetime.now(timezone.utc)
    with _session() as session:
        session.add(
            LlmRateLimit(
                provider="openrouter",
                purpose="ai_decision",
                requests_per_minute=1,
                min_gap_ms=0,
                window_started_at=old,
                requests_used=1,
                last_request_at=old,
            )
        )
        session.commit()

        out = acquire_llm_slot(
            session=session,
            provider="openrouter",
            purpose="ai_decision",
            now=now,
        )
        row = session.exec(select(LlmRateLimit)).one()

    assert out.allowed is True
    assert row.requests_used == 1
    assert row.window_started_at >= now - timedelta(seconds=1)
