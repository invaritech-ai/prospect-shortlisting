"""Procrastinate task: verify a batch of contacts via ZeroBounce."""
from __future__ import annotations

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app


@app.task(name="verify_contacts", queue="validation")
async def verify_contacts(job_id: str) -> None:
    from app.services.contact_verify_service import ContactVerifyService
    ContactVerifyService().run_verify(
        engine=get_engine(),
        job_id=job_id,
    )
