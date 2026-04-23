from __future__ import annotations

import math
import time
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.core.config import settings
from app.models import ContactFetchRuntimeControl
from app.models.pipeline import utcnow
from app.services.redis_client import get_redis

_CONTROL_SINGLETON_KEY = "default"
_PROVIDER_MIN_INTERVAL_SEC: dict[str, float] = {
    "snov": 1.0,
    "apollo": 0.6,
}


@dataclass(frozen=True)
class ProviderBackpressureDecision:
    wait_seconds: int
    reason: str | None = None


class ContactRuntimeService:
    def get_or_create_control(self, session: Session) -> ContactFetchRuntimeControl:
        control = session.exec(
            select(ContactFetchRuntimeControl).where(
                col(ContactFetchRuntimeControl.singleton_key) == _CONTROL_SINGLETON_KEY
            )
        ).first()
        if control is not None:
            return control
        control = ContactFetchRuntimeControl(
            singleton_key=_CONTROL_SINGLETON_KEY,
            auto_enqueue_enabled=settings.contact_auto_enqueue_enabled,
            auto_enqueue_paused=False,
            auto_enqueue_max_batch_size=settings.contact_auto_enqueue_max_batch_size,
            auto_enqueue_max_active_per_run=settings.contact_auto_enqueue_max_active_per_run,
            dispatcher_batch_size=settings.contact_dispatcher_batch_size,
        )
        session.add(control)
        session.commit()
        session.refresh(control)
        return control

    def update_control(
        self,
        session: Session,
        *,
        auto_enqueue_enabled: bool | None = None,
        auto_enqueue_paused: bool | None = None,
        auto_enqueue_max_batch_size: int | None = None,
        auto_enqueue_max_active_per_run: int | None = None,
        dispatcher_batch_size: int | None = None,
    ) -> ContactFetchRuntimeControl:
        control = self.get_or_create_control(session)
        if auto_enqueue_enabled is not None:
            control.auto_enqueue_enabled = auto_enqueue_enabled
        if auto_enqueue_paused is not None:
            control.auto_enqueue_paused = auto_enqueue_paused
        if auto_enqueue_max_batch_size is not None:
            control.auto_enqueue_max_batch_size = max(1, auto_enqueue_max_batch_size)
        if auto_enqueue_max_active_per_run is not None:
            control.auto_enqueue_max_active_per_run = max(1, auto_enqueue_max_active_per_run)
        if dispatcher_batch_size is not None:
            control.dispatcher_batch_size = max(1, dispatcher_batch_size)
        control.updated_at = utcnow()
        session.add(control)
        session.commit()
        session.refresh(control)
        return control

    def claim_provider_slot(self, provider: str) -> ProviderBackpressureDecision:
        normalized = (provider or "").strip().lower()
        redis = get_redis()
        if redis is None:
            return ProviderBackpressureDecision(wait_seconds=0)
        now = time.time()
        cooldown_raw = redis.get(self._cooldown_key(normalized))
        if cooldown_raw:
            cooldown_until = float(cooldown_raw.decode("utf-8"))
            if cooldown_until > now:
                return ProviderBackpressureDecision(
                    wait_seconds=max(1, math.ceil(cooldown_until - now)),
                    reason="provider_cooldown",
                )
        next_slot_raw = redis.get(self._next_slot_key(normalized))
        if next_slot_raw:
            next_slot_at = float(next_slot_raw.decode("utf-8"))
            if next_slot_at > now:
                return ProviderBackpressureDecision(
                    wait_seconds=max(1, math.ceil(next_slot_at - now)),
                    reason="provider_throttled",
                )
        interval = _PROVIDER_MIN_INTERVAL_SEC.get(normalized, 1.0)
        ttl = max(1, math.ceil(interval * 4))
        redis.setex(self._next_slot_key(normalized), ttl, str(now + interval))
        return ProviderBackpressureDecision(wait_seconds=0)

    def record_provider_success(self, provider: str) -> None:
        normalized = (provider or "").strip().lower()
        redis = get_redis()
        if redis is None:
            return
        redis.delete(self._failure_count_key(normalized))

    def record_provider_error(self, provider: str, error_code: str) -> int:
        normalized = (provider or "").strip().lower()
        redis = get_redis()
        base_delay = max(1, int(settings.contact_provider_retry_delay_sec))
        cooldown = max(base_delay, int(settings.contact_provider_cooldown_sec))
        if redis is None:
            if "rate_limited" in error_code:
                return cooldown
            return base_delay

        if "rate_limited" in error_code:
            self._set_provider_cooldown(redis, normalized, cooldown)
            return cooldown

        fail_count = redis.incr(self._failure_count_key(normalized))
        redis.expire(self._failure_count_key(normalized), cooldown)
        if fail_count >= max(1, int(settings.contact_provider_circuit_threshold)):
            self._set_provider_cooldown(redis, normalized, cooldown)
            return cooldown
        return min(cooldown, base_delay * max(1, int(fail_count)))

    def clear_provider_backpressure(self, provider: str) -> None:
        normalized = (provider or "").strip().lower()
        redis = get_redis()
        if redis is None:
            return
        redis.delete(self._cooldown_key(normalized))
        redis.delete(self._failure_count_key(normalized))

    def _set_provider_cooldown(self, redis, provider: str, delay_seconds: int) -> None:
        until = time.time() + delay_seconds
        redis.setex(self._cooldown_key(provider), delay_seconds, str(until))

    @staticmethod
    def _cooldown_key(provider: str) -> str:
        return f"contact-provider:{provider}:cooldown-until"

    @staticmethod
    def _next_slot_key(provider: str) -> str:
        return f"contact-provider:{provider}:next-slot"

    @staticmethod
    def _failure_count_key(provider: str) -> str:
        return f"contact-provider:{provider}:fail-count"
