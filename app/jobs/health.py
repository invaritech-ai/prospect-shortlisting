"""Smoke-test job to verify the Procrastinate worker can pick up tasks."""
from __future__ import annotations

import logging

from app.queue import app

logger = logging.getLogger(__name__)


@app.task(name="ping")
async def ping() -> None:
    logger.info("procrastinate ping ok")
