from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlmodel import SQLModel, Session, create_engine

from app.api.routes.companies import get_scrape_counts
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeResult


def _domain(campaign_id, domain: str, scrape_status: str | None) -> UploadedDomain:
    return UploadedDomain(
        campaign_id=campaign_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        dedupe_key=domain,
        scrape_status=scrape_status,
    )


def test_scrape_counts_returns_remaining_work_with_retryable_failed_only() -> None:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    campaign_id = uuid4()
    now = datetime.now(UTC)

    with Session(engine) as session:
        pending = _domain(campaign_id, "pending.test", None)
        queued = _domain(campaign_id, "queued.test", "queued")
        running = _domain(campaign_id, "running.test", "running")
        succeeded = _domain(campaign_id, "succeeded.test", "succeeded")
        retryable = _domain(campaign_id, "retryable.test", "failed")
        permanent = _domain(campaign_id, "permanent.test", "failed")
        session.add_all([pending, queued, running, succeeded, retryable, permanent])
        session.flush()

        session.add_all(
            [
                ScrapeResult(
                    campaign_id=campaign_id,
                    domain_id=retryable.id,
                    state="failed",
                    retryable=False,
                    updated_at=now - timedelta(minutes=1),
                ),
                ScrapeResult(
                    campaign_id=campaign_id,
                    domain_id=retryable.id,
                    state="failed",
                    retryable=True,
                    updated_at=now,
                ),
                ScrapeResult(
                    campaign_id=campaign_id,
                    domain_id=permanent.id,
                    state="failed",
                    retryable=False,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

        counts = get_scrape_counts(campaign_id=campaign_id, session=session)

    assert counts.total == 6
    assert counts.pending == 1
    assert counts.queued == 1
    assert counts.running == 1
    assert counts.succeeded == 1
    assert counts.failed == 2
    assert counts.retryable_failed == 1
    assert counts.remaining_work == 4
