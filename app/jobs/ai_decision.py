"""Procrastinate task: execute one AnalysisJob."""
from __future__ import annotations

from uuid import UUID

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app
from app.services.analysis_service import AnalysisService

_service = AnalysisService()

@app.task(name="run_ai_decision", queue="ai_decision")
async def run_ai_decision(analysis_job_id: str) -> None:
    _service.run_analysis_job(
        engine=get_engine(),
        analysis_job_id=UUID(analysis_job_id),
    )
