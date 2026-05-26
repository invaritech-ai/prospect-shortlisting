from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from app.models.core import UploadedDomain
from app.models.scrape import ScrapeBatch, ScrapeResult
from app.services import scrape_service
from app.services.scrape_service import ScrapeService


@pytest.mark.asyncio
async def test_scrape_worker_claims_queued_result_when_dispatcher_commit_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    batch_id = uuid4()
    result_id = uuid4()
    domain_id = uuid4()

    with Session(engine) as session:
        session.add(
            UploadedDomain(
                id=domain_id,
                campaign_id=campaign_id,
                raw_url="https://race.test",
                normalized_url="https://race.test",
                domain="race.test",
                dedupe_key="race.test",
                scrape_status="queued",
            )
        )
        session.add(
            ScrapeBatch(
                id=batch_id,
                campaign_id=campaign_id,
                state="running",
                selected_domain_count=1,
                queued_count=1,
            )
        )
        session.add(
            ScrapeResult(
                id=result_id,
                campaign_id=campaign_id,
                domain_id=domain_id,
                scrape_batch_id=batch_id,
                state="queued",
            )
        )
        session.commit()

    async def fake_resolve_domain(_domain: str) -> bool:
        return False

    monkeypatch.setattr(scrape_service, "resolve_domain", fake_resolve_domain)

    await ScrapeService().run_scrape(engine=engine, result_id=result_id)

    with Session(engine) as session:
        result = session.exec(select(ScrapeResult).where(ScrapeResult.id == result_id)).one()
        domain = session.exec(select(UploadedDomain).where(UploadedDomain.id == domain_id)).one()
        batch = session.exec(select(ScrapeBatch).where(ScrapeBatch.id == batch_id)).one()

    assert result.state == "failed"
    assert result.error_code == "dns_not_resolved"
    assert domain.scrape_status == "failed"
    assert batch.state == "completed"
    assert batch.failed_count == 1
