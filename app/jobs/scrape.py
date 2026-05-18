"""Procrastinate tasks: dispatch a scrape batch; scrape a single domain."""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from procrastinate import RetryStrategy
from sqlmodel import Session, col, select

from app.db.session import get_engine
from app.jobs._priority import BULK_USER  # noqa: F401
from app.models.core import UploadedDomain
from app.models.scrape import ScrapeBatch, ScrapeResult
from app.queue import app
from app.services.queue_guard import available_slots
from app.services.scrape_service import ScrapeService

logger = logging.getLogger(__name__)

_service = ScrapeService()

DISPATCH_BATCH_SIZE = 100


@app.task(
    name="scrape_domain",
    queue="scrape",
    retry=RetryStrategy(max_attempts=2, wait=60),
)
async def scrape_domain(result_id: str) -> None:
    engine = get_engine()
    await _service.run_scrape(engine=engine, result_id=UUID(result_id))


async def _defer_scrape_domain_bulk(
    *,
    priority: int,
    result_ids: list[UUID],
) -> list[BaseException | None]:
    if not result_ids:
        return []
    task = scrape_domain.configure(priority=priority)
    return list(
        await asyncio.gather(
            *(task.defer_async(result_id=str(rid)) for rid in result_ids),
            return_exceptions=True,
        )
    )


@app.task(
    name="dispatch_scrape_batch",
    queue="scrape",
    retry=RetryStrategy(max_attempts=5, wait=30),
)
async def dispatch_scrape_batch(batch_id: str) -> None:
    engine = get_engine()
    batch_uuid = UUID(batch_id)

    with Session(engine) as session:
        batch = session.get(ScrapeBatch, batch_uuid)
        if batch is None or batch.state in ("completed", "failed"):
            return
        batch.state = "dispatching"
        session.add(batch)
        session.commit()

    while True:
        with Session(engine) as session:
            pending_stmt = (
                select(ScrapeResult)
                .where(
                    col(ScrapeResult.scrape_batch_id) == batch_uuid,
                    col(ScrapeResult.state) == "queued",
                )
                .order_by(col(ScrapeResult.created_at), col(ScrapeResult.id))
                .limit(DISPATCH_BATCH_SIZE)
            )
            pending = list(session.exec(pending_stmt))

            if not pending:
                # All items dispatched — mark batch running (workers update to completed)
                batch = session.get(ScrapeBatch, batch_uuid)
                if batch is not None and batch.state not in ("completed", "failed"):
                    batch.state = "running"
                    session.add(batch)
                    session.commit()
                return

            slots = available_slots(engine, "scrape", len(pending))
            if slots == 0:
                await dispatch_scrape_batch.configure(
                    schedule_in={"seconds": 60}
                ).defer_async(batch_id=batch_id)
                return

            chunk = pending[:slots]
            result_ids = [r.id for r in chunk]

        defer_results = await _defer_scrape_domain_bulk(
            priority=BULK_USER,
            result_ids=result_ids,
        )

        queued_inc = 0
        with Session(engine) as session:
            for rid, outcome in zip(result_ids, defer_results):
                if isinstance(outcome, Exception):
                    logger.warning("dispatch_scrape_batch: defer failed for result %s: %s", rid, outcome)
                    # Leave state=queued so next dispatcher loop retries
                else:
                    queued_inc += 1

            batch = session.get(ScrapeBatch, batch_uuid)
            if batch:
                batch.queued_count += queued_inc
                session.add(batch)
            session.commit()
