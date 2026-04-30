from __future__ import annotations

import logging

from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app

logger = logging.getLogger(__name__)


@app.task(name="validate_email", queue="validation")
async def validate_email(contact_id: str) -> None:
    logger.warning("validate_email: not yet implemented")
