"""Procrastinate task stub: AI classification. Body implemented in S2 phase."""
from __future__ import annotations

import logging

from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app

logger = logging.getLogger(__name__)


@app.task(name="run_ai_decision", queue="ai_decision")
async def run_ai_decision(analysis_job_id: str) -> None:
    logger.warning("run_ai_decision: not yet implemented (job %s)", analysis_job_id)
