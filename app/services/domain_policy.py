"""Per-domain adaptive fetch policy: cadence, concurrency, backoff, circuit.

This module holds the domain state machine that keeps the scraper polite,
parallel-safe, and resilient in the face of block events. It is intentionally
self-contained so unit tests can drive it deterministically without touching
the network.

Responsibilities
----------------
* **Cadence**: enforce a jittered minimum gap between requests to the same
  origin, even when multiple worker tasks pick up URLs for that domain at
  the same time.
* **Concurrency**: cap simultaneous in-flight requests per domain.
* **Backoff**: widen the cadence window on each consecutive hostile failure
  (403 / 429 / bot-wall / timeout) and decay back on success streaks.
* **Circuit breaker**: after a threshold of consecutive hostile failures,
  refuse new requests to the domain for a cooldown window.
* **Tier mode**: track whether a domain is currently running through the
  static tier or has been escalated to the stealth tier, and decide when
  to demote it back.

The manager holds **in-process** state only (per worker). That's fine for
our topology — Celery workers are long-lived, and even if two workers pick
up the same domain they'll independently back off on block signals.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import settings
from app.core.logging import log_event
from app.services.fetch_service import HOSTILE_ERROR_CODES, FetchErrorCode


logger = logging.getLogger(__name__)


TierMode = Literal["static", "stealth"]


@dataclass
class DomainState:
    """Mutable state machine for a single domain, tracked per-worker."""

    domain: str
    tier: TierMode = "static"
    # Monotonic timestamp (time.monotonic()) before which no new request may
    # begin. Enforced by `acquire()` so cadence holds across coroutines.
    next_request_at: float = 0.0
    in_flight: int = 0
    # Consecutive hostile failures (used for backoff growth + circuit open).
    consecutive_failures: int = 0
    # Consecutive successes — drives demotion from stealth back to static.
    consecutive_successes: int = 0
    # If > now(), the domain is in circuit-open cooldown.
    cooldown_until: float = 0.0
    # Current adaptive backoff window (grows on hostile failures).
    current_backoff_sec: float = 0.0
    # Cumulative counters for telemetry.
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    escalations: int = 0
    circuit_opens: int = 0


@dataclass
class PolicyConfig:
    """Tunable knobs. Mirror `Settings` but injectable for tests."""

    min_delay_sec: float = 0.4
    max_delay_sec: float = 1.2
    max_concurrency: int = 2
    backoff_multiplier: float = 2.0
    max_backoff_sec: float = 30.0
    circuit_threshold: int = 4
    cooldown_sec: float = 90.0
    stealth_max_domains: int = 3
    demotion_streak: int = 3

    @classmethod
    def from_settings(cls) -> "PolicyConfig":
        return cls(
            min_delay_sec=settings.scrape_domain_min_delay_sec,
            max_delay_sec=settings.scrape_domain_max_delay_sec,
            max_concurrency=settings.scrape_domain_max_concurrency,
            backoff_multiplier=settings.scrape_domain_backoff_multiplier,
            max_backoff_sec=settings.scrape_domain_max_backoff_sec,
            circuit_threshold=settings.scrape_domain_circuit_threshold,
            cooldown_sec=settings.scrape_domain_cooldown_sec,
            stealth_max_domains=settings.scrape_stealth_max_domains,
            demotion_streak=settings.scrape_stealth_demotion_streak,
        )


class CircuitOpenError(RuntimeError):
    """Raised by `DomainPolicyManager.acquire` when a domain is in cooldown."""

    def __init__(self, domain: str, cooldown_remaining: float) -> None:
        self.domain = domain
        self.cooldown_remaining = cooldown_remaining
        super().__init__(
            f"circuit_open domain={domain} cooldown_remaining={cooldown_remaining:.1f}s"
        )


class DomainPolicyManager:
    """Async-safe coordinator for per-domain cadence + backoff + circuit."""

    def __init__(
        self,
        config: PolicyConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._config = config or PolicyConfig.from_settings()
        self._clock = clock
        self._jitter = jitter
        self._lock = asyncio.Lock()
        self._states: dict[str, DomainState] = {}
        self._stealth_domains: set[str] = set()

    # ── public API ──────────────────────────────────────────────────────────

    @property
    def config(self) -> PolicyConfig:
        return self._config

    def get_state(self, domain: str) -> DomainState:
        """Return (or lazily create) the state for a domain. Mutations must
        go through `acquire` / `release` / `record_*` for safety."""
        key = self._key(domain)
        state = self._states.get(key)
        if state is None:
            state = DomainState(domain=key)
            self._states[key] = state
        return state

    def snapshot(self) -> dict[str, DomainState]:
        """Return a shallow copy of current per-domain states (for telemetry)."""
        return dict(self._states)

    async def acquire(self, domain: str) -> float:
        """Reserve a slot for the next request to `domain`.

        Blocks until (a) the cadence/backoff delay has elapsed and (b) a
        concurrency slot is free. Raises `CircuitOpenError` immediately if the
        domain is in its cooldown window.

        Returns the wait duration (seconds) actually spent in cadence. Callers
        MUST pair every `acquire()` with a `release()` in a `try/finally`.
        """
        # Step 1: fast-path circuit check + reserve a concurrency slot + compute
        # the next available start time, all under a single lock.
        start_wait = self._clock()
        while True:
            async with self._lock:
                state = self.get_state(domain)
                now = self._clock()

                cooldown_remaining = state.cooldown_until - now
                if cooldown_remaining > 0:
                    raise CircuitOpenError(domain, cooldown_remaining)

                if state.in_flight < self._config.max_concurrency:
                    # Reserve a slot; still need to honor cadence.
                    state.in_flight += 1
                    state.attempts += 1
                    wait_until = max(state.next_request_at, now)
                    # Schedule the *next* start at wait_until + jitter window
                    # so parallel callers interleave cleanly.
                    gap = self._jittered_gap(state)
                    state.next_request_at = wait_until + gap
                    break
                # Concurrency full — wait briefly and retry.
            await asyncio.sleep(self._recheck_interval())

        # Step 2: sleep outside the lock until our reserved start time.
        delay = max(0.0, wait_until - self._clock())
        if delay > 0:
            try:
                await asyncio.sleep(delay)
            except BaseException:
                async with self._lock:
                    state = self.get_state(domain)
                    if state.in_flight > 0:
                        state.in_flight -= 1
                    if state.attempts > 0:
                        state.attempts -= 1
                raise
        return self._clock() - start_wait

    async def release(self, domain: str) -> None:
        """Release the concurrency slot. Safe to call in a `finally` clause."""
        async with self._lock:
            state = self.get_state(domain)
            if state.in_flight > 0:
                state.in_flight -= 1

    async def record_result(
        self,
        domain: str,
        error_code: str,
        *,
        tier: TierMode = "static",
    ) -> None:
        """Feed an error-code outcome back into the domain policy.

        Updates success/failure streaks, adjusts the adaptive backoff window,
        and opens the circuit breaker if the hostile-failure streak exceeds
        `circuit_threshold`. Non-hostile failures (e.g. dns_not_resolved,
        non_html) do NOT count against the circuit — they're treated as
        target-specific and propagate up.
        """
        async with self._lock:
            state = self.get_state(domain)
            if error_code == FetchErrorCode.OK:
                state.successes += 1
                state.consecutive_successes += 1
                state.consecutive_failures = 0
                # Decay backoff window: on every clean success chop it in half,
                # floor at zero. This keeps the cadence responsive if the
                # server recovers quickly.
                if state.current_backoff_sec > 0:
                    state.current_backoff_sec = max(
                        0.0, state.current_backoff_sec / self._config.backoff_multiplier
                    )
                return

            state.failures += 1
            state.consecutive_successes = 0

            if error_code in HOSTILE_ERROR_CODES or error_code == FetchErrorCode.TIMEOUT:
                state.consecutive_failures += 1
                # Grow the backoff window. Use the *greater* of (multiplier of
                # current backoff) or (a reasonable base of max_delay_sec) so
                # the first hostile hit still produces a visible slowdown.
                new_backoff = max(
                    self._config.max_delay_sec,
                    state.current_backoff_sec * self._config.backoff_multiplier,
                )
                state.current_backoff_sec = min(
                    new_backoff, self._config.max_backoff_sec
                )

                if state.consecutive_failures >= self._config.circuit_threshold:
                    now = self._clock()
                    state.cooldown_until = now + self._config.cooldown_sec
                    state.circuit_opens += 1
                    # Reset the failure streak — after the cooldown elapses we
                    # give the domain a clean slate so it can probe again.
                    state.consecutive_failures = 0
                    log_event(
                        logger,
                        "fetch_circuit_open",
                        domain=domain,
                        tier=tier,
                        cooldown_sec=self._config.cooldown_sec,
                    )

    async def mark_escalated(self, domain: str) -> bool:
        """Move a domain to the stealth tier. Returns False if escalation is
        refused (e.g. worker-level stealth cap reached)."""
        async with self._lock:
            state = self.get_state(domain)
            if state.tier == "stealth":
                return True
            if len(self._stealth_domains) >= self._config.stealth_max_domains:
                log_event(
                    logger,
                    "fetch_stealth_escalation_refused",
                    domain=domain,
                    stealth_domains=len(self._stealth_domains),
                    cap=self._config.stealth_max_domains,
                )
                return False
            state.tier = "stealth"
            state.escalations += 1
            state.consecutive_successes = 0
            self._stealth_domains.add(self._key(domain))
            log_event(logger, "fetch_stealth_escalate", domain=domain)
            return True

    async def maybe_demote(self, domain: str) -> bool:
        """If a stealth domain has enough consecutive successes, demote it back
        to the static tier. Returns True when demotion actually occurs."""
        async with self._lock:
            state = self.get_state(domain)
            if state.tier != "stealth":
                return False
            if state.consecutive_successes < self._config.demotion_streak:
                return False
            state.tier = "static"
            self._stealth_domains.discard(self._key(domain))
            log_event(logger, "fetch_stealth_demote", domain=domain,
                      streak=state.consecutive_successes)
            return True

    def current_tier(self, domain: str) -> TierMode:
        return self.get_state(domain).tier

    def is_circuit_open(self, domain: str) -> bool:
        state = self.get_state(domain)
        return state.cooldown_until > self._clock()

    # ── internals ───────────────────────────────────────────────────────────

    def _jittered_gap(self, state: DomainState) -> float:
        base = self._jitter(self._config.min_delay_sec, self._config.max_delay_sec)
        return base + state.current_backoff_sec

    def _recheck_interval(self) -> float:
        # Small sleep while waiting for a concurrency slot — kept short so the
        # cadence window remains the actual throttle.
        return max(0.05, self._config.min_delay_sec / 4.0)

    @staticmethod
    def _key(domain: str) -> str:
        return (domain or "").strip().lower()


# ── Module-level singleton ──────────────────────────────────────────────────
# Celery task code should import and use this shared instance so all async
# fetch calls within a worker coordinate cleanly. Tests construct their own
# DomainPolicyManager with injected clock/jitter for determinism.

_default_manager: DomainPolicyManager | None = None


def get_default_manager() -> DomainPolicyManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = DomainPolicyManager()
    return _default_manager


def reset_default_manager_for_tests() -> None:
    """Clear the module-level manager — used in tests to guarantee isolation."""
    global _default_manager
    _default_manager = None
