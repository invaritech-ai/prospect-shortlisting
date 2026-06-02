"""Procrastinate task: run one S3 email-fetch batch."""
from __future__ import annotations

from uuid import UUID

from procrastinate import RetryStrategy
from sqlmodel import Session

from app.db.session import get_engine
from app.jobs._priority import BULK_USER  # noqa: F401
from app.queue import app
from app.services.email_fetch_service import EmailFetchService


@app.task(
    name="run_email_fetch_batch",
    queue="contact_fetch",
    retry=RetryStrategy(max_attempts=2, wait=60),
)
async def run_email_fetch_batch(batch_id: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        EmailFetchService().run_batch(session=session, batch_id=UUID(batch_id))
