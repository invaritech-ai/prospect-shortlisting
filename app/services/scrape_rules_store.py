from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import JobEvent
from app.models.pipeline import JobType, utcnow
from app.services.redis_client import get_redis

_RULES_TTL_SEC = 30 * 24 * 60 * 60


def _key(job_id: str) -> str:
    return f"scrape-rules:{job_id}"


def store_rules_for_job(*, job_id: str, rules: dict[str, Any] | None) -> None:
    if not rules:
        return
    redis = get_redis()
    if redis is None:
        return
    redis.setex(_key(job_id), _RULES_TTL_SEC, json.dumps(rules, default=str))


def persist_rules_for_job(*, session: Session, job_id: UUID, rules: dict[str, Any] | None) -> None:
    if not rules:
        return
    store_rules_for_job(job_id=str(job_id), rules=rules)
    session.add(
        JobEvent(
            job_type=JobType.CRAWL,
            job_id=job_id,
            to_state="created",
            event_type="scrape_rules_saved",
            payload_json={"scrape_rules": rules},
            created_at=utcnow(),
        )
    )
    session.commit()


def load_rules_for_job(*, session: Session | None = None, job_id: UUID | str) -> dict[str, Any] | None:
    job_id_str = str(job_id)
    job_uuid = UUID(job_id_str)
    redis = get_redis()
    if redis is not None:
        raw = redis.get(_key(job_id_str))
        if raw:
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except Exception:  # noqa: BLE001
                parsed = None
            if isinstance(parsed, dict):
                return parsed

    if session is None:
        return None
    row = session.exec(
        select(JobEvent.payload_json)
        .where(
            col(JobEvent.job_type) == JobType.CRAWL,
            col(JobEvent.job_id) == job_uuid,
            col(JobEvent.event_type) == "scrape_rules_saved",
        )
        .order_by(col(JobEvent.created_at).desc())
        .limit(1)
    ).first()
    if not row:
        return None
    rules = row.get("scrape_rules") if isinstance(row, dict) else None
    if not isinstance(rules, dict):
        return None
    return rules
