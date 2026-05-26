from __future__ import annotations

import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import bindparam, func, text
from sqlmodel import Session, col, select

from app.api.schemas.scrape import ScrapeJobStatusRead
from app.models.scrape import ScrapeBatch, ScrapeResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _eta_seconds(*, batch: ScrapeBatch, terminal: int, selected: int) -> float | None:
    remaining = selected - terminal
    if remaining <= 0:
        return 0.0
    elapsed_secs = (_utcnow() - batch.created_at).total_seconds()
    if elapsed_secs < 5 or terminal <= 0:
        return None
    rate_per_sec = terminal / elapsed_secs
    if rate_per_sec <= 0:
        return None
    return float(math.ceil(remaining / rate_per_sec))


def _queue_counts_for_results(session: Session, result_ids: list[UUID]) -> dict[str, int]:
    if not result_ids:
        return {}
    if session.get_bind().dialect.name != "postgresql":
        # SQLite test runs do not include the Procrastinate schema.
        return {}
    stmt = (
        text(
            """
            select status::text, count(*)
            from procrastinate_jobs
            where task_name = 'scrape_domain'
              and args->>'result_id' in :result_ids
            group by status::text
            """
        ).bindparams(bindparam("result_ids", expanding=True))
    )
    rows = session.execute(stmt, {"result_ids": [str(rid) for rid in result_ids]}).all()
    return {str(status): int(count) for status, count in rows}


def build_scrape_job_status(
    *,
    session: Session,
    batch_id: UUID,
) -> ScrapeJobStatusRead | None:
    batch = session.get(ScrapeBatch, batch_id)
    if batch is None:
        return None

    state_rows = session.exec(
        select(col(ScrapeResult.state), func.count(ScrapeResult.id))
        .where(col(ScrapeResult.scrape_batch_id) == batch_id)
        .group_by(col(ScrapeResult.state))
    ).all()
    by_state = {str(state): int(count) for state, count in state_rows}

    result_ids = list(
        session.exec(
            select(col(ScrapeResult.id)).where(col(ScrapeResult.scrape_batch_id) == batch_id)
        ).all()
    )
    queue_counts = _queue_counts_for_results(session, result_ids)

    selected = len(result_ids)
    queued = by_state.get("queued", 0)
    running = by_state.get("running", 0) + by_state.get("dispatched", 0)
    succeeded = by_state.get("succeeded", 0)
    failed = by_state.get("failed", 0)
    terminal = succeeded + failed

    queue_todo = queue_counts.get("todo", 0)
    queue_doing = queue_counts.get("doing", 0)
    non_terminal = queued + running
    live_queue = queue_todo + queue_doing

    inconsistency_reason = None
    if selected > 0 and terminal >= selected:
        state = "completed"
    elif non_terminal > 0 and live_queue > 0:
        state = "running"
    elif non_terminal > 0 and live_queue == 0:
        state = "inconsistent"
        inconsistency_reason = "non_terminal_results_without_live_queue_jobs"
    else:
        state = "queued"

    return ScrapeJobStatusRead(
        batch_id=batch.id,
        campaign_id=batch.campaign_id,
        state=state,
        selected=selected,
        queued=queued,
        running=running,
        succeeded=succeeded,
        failed=failed,
        terminal=terminal,
        queue_todo=queue_todo,
        queue_doing=queue_doing,
        queue_succeeded=queue_counts.get("succeeded", 0),
        queue_failed=queue_counts.get("failed", 0),
        queue_cancelled=queue_counts.get("cancelled", 0),
        queue_aborting=queue_counts.get("aborting", 0),
        queue_aborted=queue_counts.get("aborted", 0),
        eta_seconds=_eta_seconds(batch=batch, terminal=terminal, selected=selected) if state == "running" else None,
        inconsistency_reason=inconsistency_reason,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )
