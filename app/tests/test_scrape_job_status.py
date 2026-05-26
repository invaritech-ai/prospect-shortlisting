from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlmodel import SQLModel, Session, create_engine

from app.models.scrape import ScrapeBatch, ScrapeResult
from app.services.scrape_job_status import build_scrape_job_status


def test_status_completed_when_all_results_terminal() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    batch_id = uuid4()
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add(
            ScrapeBatch(
                id=batch_id,
                campaign_id=campaign_id,
                selected_domain_count=2,
                created_at=now - timedelta(minutes=3),
            )
        )
        session.add(
            ScrapeResult(
                campaign_id=campaign_id,
                domain_id=uuid4(),
                scrape_batch_id=batch_id,
                state="succeeded",
            )
        )
        session.add(
            ScrapeResult(
                campaign_id=campaign_id,
                domain_id=uuid4(),
                scrape_batch_id=batch_id,
                state="failed",
            )
        )
        session.commit()

        status = build_scrape_job_status(session=session, batch_id=batch_id)

    assert status is not None
    assert status.state == "completed"
    assert status.selected == 2
    assert status.terminal == 2
    assert status.inconsistency_reason is None


def test_status_inconsistent_when_non_terminal_results_have_no_live_queue_jobs() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    batch_id = uuid4()

    with Session(engine) as session:
        session.add(
            ScrapeBatch(
                id=batch_id,
                campaign_id=campaign_id,
                selected_domain_count=1,
            )
        )
        session.add(
            ScrapeResult(
                campaign_id=campaign_id,
                domain_id=uuid4(),
                scrape_batch_id=batch_id,
                state="running",
            )
        )
        session.commit()

        status = build_scrape_job_status(session=session, batch_id=batch_id)

    assert status is not None
    assert status.state == "inconsistent"
    assert status.running == 1
    assert status.inconsistency_reason == "non_terminal_results_without_live_queue_jobs"
