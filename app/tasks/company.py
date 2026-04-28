from __future__ import annotations

import logging
from uuid import UUID

from app.celery_app import app
from app.core.logging import log_event
from app.db.session import get_engine

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="app.tasks.company.cascade_delete_companies",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=300,
    time_limit=360,
)
def cascade_delete_companies(self, company_ids: list[str], campaign_id: str) -> None:
    from sqlmodel import Session
    from app.services.company_service import cascade_delete_companies as _cascade_delete

    log_event(logger, "cascade_delete_started",
              company_count=len(company_ids), campaign_id=campaign_id,
              worker=self.request.hostname)

    with Session(get_engine()) as session:
        _cascade_delete(
            session,
            [UUID(cid) for cid in company_ids],
            UUID(campaign_id),
        )

    log_event(logger, "cascade_delete_done",
              company_count=len(company_ids), campaign_id=campaign_id)
