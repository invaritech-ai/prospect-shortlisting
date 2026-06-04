"""Procrastinate task: run one S4 email verification batch."""
from __future__ import annotations

from uuid import UUID

from procrastinate import RetryStrategy
from sqlmodel import Session

from app.db.session import get_engine
from app.jobs._priority import BULK_USER  # noqa: F401
from app.queue import app
from app.services.email_verification_service import EmailVerificationService


@app.task(
    name="run_email_verification_batch",
    queue="validation",
    retry=RetryStrategy(max_attempts=2, wait=60),
)
async def run_email_verification_batch(batch_id: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        EmailVerificationService().run_batch(session=session, batch_id=UUID(batch_id))
