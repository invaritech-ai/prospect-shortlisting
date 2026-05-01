"""Procrastinate task: execute one ContactFetchJob."""
from __future__ import annotations

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app


@app.task(name="fetch_contacts", queue="contact_fetch")
async def fetch_contacts(contact_fetch_job_id: str) -> None:
    from app.services.contact_fetch_service import ContactFetchService
    ContactFetchService().run_contact_fetch_job(
        engine=get_engine(),
        contact_fetch_job_id=contact_fetch_job_id,
    )
