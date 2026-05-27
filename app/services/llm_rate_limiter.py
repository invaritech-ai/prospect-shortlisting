from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, select

from app.models.base import coerce_utc_datetime, utcnow
from app.models.llm_rate_limit import LlmRateLimit

DEFAULT_REQUESTS_PER_MINUTE = 12
DEFAULT_MIN_GAP_MS = 5000


@dataclass(frozen=True)
class LlmSlotAcquireResult:
    allowed: bool
    retry_after_ms: int = 0


def _aware(value: datetime) -> datetime:
    return coerce_utc_datetime(value)


def acquire_llm_slot(
    *,
    session: Session,
    provider: str,
    purpose: str,
    now: datetime | None = None,
) -> LlmSlotAcquireResult:
    """Try to acquire one global LLM request slot.

    The transaction is intentionally short. Callers sleep outside this function
    when retry_after_ms is returned.
    """
    current = _aware(now or utcnow())
    stmt = select(LlmRateLimit).where(
        col(LlmRateLimit.provider) == provider,
        col(LlmRateLimit.purpose) == purpose,
    )
    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update()

    bucket = session.exec(stmt).first()
    if bucket is None:
        bucket = LlmRateLimit(
            provider=provider,
            purpose=purpose,
            requests_per_minute=DEFAULT_REQUESTS_PER_MINUTE,
            min_gap_ms=DEFAULT_MIN_GAP_MS,
            window_started_at=current,
            requests_used=0,
        )
        session.add(bucket)
        session.flush()

    window_started_at = _aware(bucket.window_started_at)
    if current - window_started_at >= timedelta(minutes=1):
        bucket.window_started_at = current
        bucket.requests_used = 0
        window_started_at = current

    waits: list[int] = []
    if bucket.requests_used >= bucket.requests_per_minute:
        reset_at = window_started_at + timedelta(minutes=1)
        waits.append(max(1, int((reset_at - current).total_seconds() * 1000)))

    if bucket.last_request_at is not None and bucket.min_gap_ms > 0:
        last = _aware(bucket.last_request_at)
        elapsed_ms = int((current - last).total_seconds() * 1000)
        if elapsed_ms < bucket.min_gap_ms:
            waits.append(bucket.min_gap_ms - elapsed_ms)

    if waits:
        session.commit()
        return LlmSlotAcquireResult(allowed=False, retry_after_ms=max(waits))

    bucket.requests_used += 1
    bucket.last_request_at = current
    bucket.updated_at = current
    session.add(bucket)
    session.commit()
    return LlmSlotAcquireResult(allowed=True, retry_after_ms=0)


def wait_for_llm_slot(
    *,
    session_factory,
    provider: str = "openrouter",
    purpose: str = "ai_decision",
) -> None:
    while True:
        with session_factory() as session:
            result = acquire_llm_slot(session=session, provider=provider, purpose=purpose)
        if result.allowed:
            return
        time.sleep(max(result.retry_after_ms, 1) / 1000)
