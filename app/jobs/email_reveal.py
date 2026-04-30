from __future__ import annotations

import logging

from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app

logger = logging.getLogger(__name__)


@app.task(name="reveal_email", queue="email_reveal")
async def reveal_email(contact_id: str) -> None:
    logger.warning("reveal_email: not yet implemented")
