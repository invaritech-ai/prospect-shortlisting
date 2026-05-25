from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlmodel import Session, select

from app.jobs import scrape as scrape_jobs
from app.models.scrape import ScrapeBatch, ScrapeResult


@pytest.mark.asyncio
async def test_dispatch_marks_results_dispatched_after_defer(monkeypatch) -> None:
    from sqlmodel import SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    batch_id = uuid4()
    result_id = uuid4()

    with Session(engine) as session:
        session.add(
            ScrapeBatch(
                id=batch_id,
                campaign_id=uuid4(),
                state="queued",
                selected_domain_count=1,
            )
        )
        session.add(
            ScrapeResult(
                id=result_id,
                campaign_id=uuid4(),
                domain_id=uuid4(),
                scrape_batch_id=batch_id,
                state="queued",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

    monkeypatch.setattr(scrape_jobs, "get_engine", lambda: engine)
    monkeypatch.setattr(scrape_jobs, "available_slots", lambda *_args: 1)

    deferred: list[str] = []

    async def fake_defer_bulk(*, priority: int, result_ids: list) -> list[BaseException | None]:
        deferred.extend(str(rid) for rid in result_ids)
        return [None for _ in result_ids]

    monkeypatch.setattr(scrape_jobs, "_defer_scrape_domain_bulk", fake_defer_bulk)

    await scrape_jobs.dispatch_scrape_batch(batch_id=str(batch_id))

    with Session(engine) as session:
        result = session.exec(select(ScrapeResult).where(ScrapeResult.id == result_id)).one()
        batch = session.exec(select(ScrapeBatch).where(ScrapeBatch.id == batch_id)).one()

    assert deferred == [str(result_id)]
    assert result.state == "dispatched"
    assert batch.queued_count == 1
