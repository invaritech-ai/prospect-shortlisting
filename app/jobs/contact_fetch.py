from __future__ import annotations

import logging

from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app

logger = logging.getLogger(__name__)


@app.task(name="fetch_contacts", queue="contact_fetch")
async def fetch_contacts(company_id: str, campaign_id: str) -> None:
    logger.warning("fetch_contacts: not yet implemented")
