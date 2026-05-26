from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from app.api.routes import scrape_runs
from app.api.schemas.scrape import ScrapeBatchCreate
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeResult


@pytest.mark.asyncio
async def test_create_scrape_job_creates_results_and_enqueues_each_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    domain_id = uuid4()

    with Session(engine) as session:
        session.add(
            UploadedDomain(
                id=domain_id,
                campaign_id=campaign_id,
                raw_url="https://example.com",
                normalized_url="https://example.com",
                domain="example.com",
                dedupe_key="example.com",
            )
        )
        session.commit()

    enqueued: list[str] = []

    async def fake_enqueue(result_ids):
        enqueued.extend(str(result_id) for result_id in result_ids)

    monkeypatch.setattr(scrape_runs, "is_procrastinate_schema_ready", lambda _engine: True)
    monkeypatch.setattr(scrape_runs, "get_engine", lambda: engine)
    monkeypatch.setattr(scrape_runs, "_enqueue_scrape_results", fake_enqueue)

    with Session(engine) as session:
        batch = await scrape_runs.create_scrape_job(
            body=ScrapeBatchCreate(campaign_id=campaign_id, domain_ids=[domain_id]),
            session=session,
        )
        results = session.exec(
            select(ScrapeResult).where(ScrapeResult.scrape_batch_id == batch.id)
        ).all()

    assert batch.selected_domain_count == 1
    assert len(results) == 1
    assert results[0].state == "queued"
    assert enqueued == [str(results[0].id)]
