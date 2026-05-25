from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import scrape_runs
from app.api.schemas.scrape import ScrapeBatchCreate


class _NoOpSession:
    """Session stand-in to ensure queue gate returns before DB access."""

    def exec(self, *_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("Session access should not occur when queue schema is unavailable")

    def add(self, *_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("No rows should be added when queue schema is unavailable")

    def add_all(self, *_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("No rows should be added when queue schema is unavailable")

    def commit(self, *_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("No commit should occur when queue schema is unavailable")

    def flush(self, *_args, **_kwargs):  # pragma: no cover - should never be called
        raise AssertionError("No flush should occur when queue schema is unavailable")


@pytest.mark.asyncio
async def test_create_scrape_batch_returns_503_when_queue_schema_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scrape_runs, "is_procrastinate_schema_ready", lambda _engine: False)

    with pytest.raises(HTTPException) as exc_info:
        await scrape_runs.create_scrape_batch(
            body=ScrapeBatchCreate(campaign_id=uuid4(), domain_ids=[]),
            session=_NoOpSession(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 503
    assert "Queue schema is not initialized" in str(exc_info.value.detail)
