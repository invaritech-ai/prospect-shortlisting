"""Server-Sent Events stream for live job-event updates.

Endpoint: GET /v1/campaigns/{campaign_id}/events/stream

Pushes one SSE message per `job_events` row inserted, scoped to the
requested campaign. Backed by `event_pubsub` (a single global
LISTEN/NOTIFY connection that fans out to per-client async queues),
so N connected clients share one DB connection — no polling, no
extra writes.

This route is purely additive: existing polling endpoints
(`/v1/queue-history`, stage panels) are unchanged and remain the
source of truth on initial load.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlmodel import Session

from app.db.session import get_session
from app.services.event_pubsub import pubsub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["events"])

_HEARTBEAT_SEC = 15.0
_CACHE_MAX = 4096

# (job_type, job_id) -> campaign_id (or None if unresolvable / no campaign)
_campaign_cache: "OrderedDict[tuple[str, str], str | None]" = OrderedDict()


def _cache_get(key: tuple[str, str]) -> tuple[bool, str | None]:
    if key in _campaign_cache:
        _campaign_cache.move_to_end(key)
        return True, _campaign_cache[key]
    return False, None


def _cache_put(key: tuple[str, str], value: str | None) -> None:
    _campaign_cache[key] = value
    _campaign_cache.move_to_end(key)
    while len(_campaign_cache) > _CACHE_MAX:
        _campaign_cache.popitem(last=False)


_RESOLVE_SQL: dict[str, str] = {
    "crawl": (
        "SELECT u.campaign_id::text FROM crawl_jobs j "
        "JOIN companies c ON c.id = j.company_id "
        "JOIN uploads u ON u.id = c.upload_id "
        "WHERE j.id = :jid"
    ),
    "analysis": (
        "SELECT u.campaign_id::text FROM analysis_jobs j "
        "JOIN uploads u ON u.id = j.upload_id "
        "WHERE j.id = :jid"
    ),
    "contact_fetch": (
        "SELECT u.campaign_id::text FROM contact_fetch_jobs j "
        "JOIN companies c ON c.id = j.company_id "
        "JOIN uploads u ON u.id = c.upload_id "
        "WHERE j.id = :jid"
    ),
}

_STAGE_LABEL: dict[str, str] = {
    "crawl": "s1",
    "analysis": "s2",
    "contact_fetch": "s3",
}


def _resolve_campaign(session: Session, job_type: str, job_id: str) -> str | None:
    key = (job_type, job_id)
    hit, val = _cache_get(key)
    if hit:
        return val
    sql = _RESOLVE_SQL.get(job_type)
    if sql is None:
        _cache_put(key, None)
        return None
    try:
        row = session.exec(text(sql).bindparams(jid=job_id)).first()  # type: ignore[arg-type]
    except Exception as exc:
        logger.debug("resolve_campaign failed for %s/%s: %s", job_type, job_id, exc)
        return None
    val = row[0] if row else None
    _cache_put(key, val)
    return val


def _format_sse(data: dict) -> bytes:
    return f"data: {json.dumps(data, default=str)}\n\n".encode("utf-8")


@router.get("/campaigns/{campaign_id}/events/stream")
async def stream_campaign_events(
    campaign_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    if pubsub._task is None:  # listener not started — feature unavailable
        raise HTTPException(status_code=503, detail="event stream not available")

    target_campaign = str(campaign_id)

    async def gen() -> AsyncIterator[bytes]:
        async with pubsub.subscribe() as q:
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_SEC)
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
                    continue

                job_type = str(payload.get("job_type") or "")
                job_id = str(payload.get("job_id") or "")
                if not job_type or not job_id:
                    continue

                resolved = _resolve_campaign(session, job_type, job_id)
                if resolved != target_campaign:
                    continue

                # scrape_batch events carry campaign_id directly — no DB join needed
                if job_type == "scrape_batch":
                    if str(payload.get("campaign_id") or "") != target_campaign:
                        continue
                    out = {
                        "stage": "s1",
                        "event_type": "scrape_batch",
                        "batch_id": payload.get("batch_id"),
                        "campaign_id": payload.get("campaign_id"),
                        "state": payload.get("state"),
                        "selected_domain_count": payload.get("selected_domain_count"),
                        "success_count": payload.get("success_count"),
                        "failed_count": payload.get("failed_count"),
                        "queued_count": payload.get("queued_count"),
                        "finished_at": payload.get("finished_at"),
                    }
                    yield _format_sse(out)
                    continue

                resolved = _resolve_campaign(session, job_type, job_id)
                if resolved != target_campaign:
                    continue

                out = {
                    "id": payload.get("id"),
                    "stage": _STAGE_LABEL.get(job_type, job_type),
                    "job_id": job_id,
                    "from_state": payload.get("from_state"),
                    "to_state": payload.get("to_state"),
                    "event_type": payload.get("event_type"),
                    "created_at": payload.get("created_at"),
                }
                yield _format_sse(out)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # disable nginx proxy buffering
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
