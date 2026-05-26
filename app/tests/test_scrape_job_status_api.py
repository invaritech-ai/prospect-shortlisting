from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

from app.api.routes.scrape_runs import get_active_batch, get_scrape_job_status
from app.models.scrape import ScrapeBatch, ScrapeResult


def test_get_scrape_job_status_returns_projection() -> None:
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
                state="succeeded",
            )
        )
        session.commit()

        status = get_scrape_job_status(batch_id=batch_id, session=session)

    assert status.state == "completed"
    assert status.succeeded == 1


def test_get_scrape_job_status_404_for_missing_batch() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        try:
            get_scrape_job_status(batch_id=uuid4(), session=session)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Expected HTTPException")


def test_active_batch_ignores_completed_latest_batch() -> None:
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
                state="succeeded",
            )
        )
        session.commit()

        active = get_active_batch(campaign_id=campaign_id, session=session)

    assert active is None
