from __future__ import annotations

from app.db.session import get_engine
from app.jobs._priority import BULK_PIPELINE  # noqa: F401
from app.queue import app


@app.task(name="reveal_email", queue="email_reveal")
async def reveal_email(contact_id: str) -> None:
    from app.services.email_reveal_service import EmailRevealService

    EmailRevealService().run_reveal(
        engine=get_engine(),
        contact_id=contact_id,
    )
