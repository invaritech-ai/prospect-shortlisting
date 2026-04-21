"""Unit tests for `DomainPolicyManager` — cadence, concurrency, backoff, circuit."""
from __future__ import annotations

import asyncio

import pytest

from app.services.domain_policy import (
    CircuitOpenError,
    DomainPolicyManager,
    PolicyConfig,
)
from app.services.fetch_service import FetchErrorCode


@pytest.fixture
def fast_config() -> PolicyConfig:
    return PolicyConfig(
        min_delay_sec=0.0,
        max_delay_sec=0.0,
        max_concurrency=2,
        backoff_multiplier=2.0,
        max_backoff_sec=8.0,
        circuit_threshold=3,
        cooldown_sec=60.0,
        stealth_max_domains=2,
        demotion_streak=2,
    )


class _FakeClock:
    """Deterministic monotonic clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _fixed_jitter(_lo: float, _hi: float) -> float:
    return 0.0


@pytest.mark.asyncio
async def test_acquire_and_release_tracks_in_flight(fast_config: PolicyConfig) -> None:
    clock = _FakeClock()
    mgr = DomainPolicyManager(fast_config, clock=clock, jitter=_fixed_jitter)

    await mgr.acquire("example.com")
    assert mgr.get_state("example.com").in_flight == 1
    await mgr.release("example.com")
    assert mgr.get_state("example.com").in_flight == 0


@pytest.mark.asyncio
async def test_concurrency_cap_blocks_third_caller(fast_config: PolicyConfig) -> None:
    clock = _FakeClock()
    mgr = DomainPolicyManager(fast_config, clock=clock, jitter=_fixed_jitter)

    await mgr.acquire("example.com")
    await mgr.acquire("example.com")
    assert mgr.get_state("example.com").in_flight == 2

    # Third caller should block until a slot frees up.
    third = asyncio.create_task(mgr.acquire("example.com"))
    await asyncio.sleep(0.15)
    assert not third.done(), "third acquire should be blocked on concurrency cap"

    await mgr.release("example.com")
    await asyncio.wait_for(third, timeout=1.5)
    await mgr.release("example.com")
    await mgr.release("example.com")


@pytest.mark.asyncio
async def test_hostile_failures_grow_backoff_and_open_circuit(
    fast_config: PolicyConfig,
) -> None:
    clock = _FakeClock()
    mgr = DomainPolicyManager(fast_config, clock=clock, jitter=_fixed_jitter)

    for _ in range(fast_config.circuit_threshold):
        await mgr.record_result("hostile.com", FetchErrorCode.BOT_PROTECTION)

    state = mgr.get_state("hostile.com")
    assert state.circuit_opens == 1
    assert mgr.is_circuit_open("hostile.com") is True

    with pytest.raises(CircuitOpenError):
        await mgr.acquire("hostile.com")

    # After cooldown elapses, domain is reopenable.
    clock.advance(fast_config.cooldown_sec + 1)
    assert mgr.is_circuit_open("hostile.com") is False
    await mgr.acquire("hostile.com")
    await mgr.release("hostile.com")


@pytest.mark.asyncio
async def test_success_decays_backoff() -> None:
    clock = _FakeClock()
    cfg = PolicyConfig(
        min_delay_sec=0.0,
        max_delay_sec=2.0,
        max_concurrency=2,
        backoff_multiplier=2.0,
        max_backoff_sec=8.0,
        circuit_threshold=3,
        cooldown_sec=60.0,
        stealth_max_domains=2,
        demotion_streak=2,
    )
    mgr = DomainPolicyManager(cfg, clock=clock, jitter=_fixed_jitter)

    await mgr.record_result("flaky.com", FetchErrorCode.RATE_LIMITED)
    before = mgr.get_state("flaky.com").current_backoff_sec
    assert before > 0.0

    await mgr.record_result("flaky.com", FetchErrorCode.OK)
    after = mgr.get_state("flaky.com").current_backoff_sec
    assert after < before


@pytest.mark.asyncio
async def test_ok_result_clears_failure_streak(fast_config: PolicyConfig) -> None:
    clock = _FakeClock()
    mgr = DomainPolicyManager(fast_config, clock=clock, jitter=_fixed_jitter)

    await mgr.record_result("recovering.com", FetchErrorCode.BOT_PROTECTION)
    await mgr.record_result("recovering.com", FetchErrorCode.OK)
    state = mgr.get_state("recovering.com")
    assert state.consecutive_failures == 0
    assert state.consecutive_successes == 1


@pytest.mark.asyncio
async def test_non_hostile_failures_dont_trigger_circuit(fast_config: PolicyConfig) -> None:
    clock = _FakeClock()
    mgr = DomainPolicyManager(fast_config, clock=clock, jitter=_fixed_jitter)

    for _ in range(10):
        await mgr.record_result("dead.com", FetchErrorCode.NOT_FOUND)

    assert mgr.is_circuit_open("dead.com") is False
    assert mgr.get_state("dead.com").consecutive_failures == 0


@pytest.mark.asyncio
async def test_escalation_honors_worker_cap(fast_config: PolicyConfig) -> None:
    clock = _FakeClock()
    mgr = DomainPolicyManager(fast_config, clock=clock, jitter=_fixed_jitter)

    assert await mgr.mark_escalated("a.com") is True
    assert await mgr.mark_escalated("b.com") is True
    # fast_config.stealth_max_domains == 2 so this should be refused.
    assert await mgr.mark_escalated("c.com") is False
    assert mgr.current_tier("c.com") == "static"


@pytest.mark.asyncio
async def test_demotion_requires_success_streak(fast_config: PolicyConfig) -> None:
    clock = _FakeClock()
    mgr = DomainPolicyManager(fast_config, clock=clock, jitter=_fixed_jitter)

    assert await mgr.mark_escalated("boosted.com") is True
    assert await mgr.maybe_demote("boosted.com") is False  # no streak yet

    await mgr.record_result("boosted.com", FetchErrorCode.OK)
    assert await mgr.maybe_demote("boosted.com") is False  # 1 < threshold

    await mgr.record_result("boosted.com", FetchErrorCode.OK)
    assert await mgr.maybe_demote("boosted.com") is True
    assert mgr.current_tier("boosted.com") == "static"


@pytest.mark.asyncio
async def test_cadence_enforces_minimum_gap() -> None:
    # Use a real (non-zero) delay window and a mutable clock-driven jitter
    # to assert the scheduled next_request_at is pushed forward.
    config = PolicyConfig(
        min_delay_sec=0.5, max_delay_sec=0.5, max_concurrency=4,
        backoff_multiplier=2.0, max_backoff_sec=2.0,
        circuit_threshold=3, cooldown_sec=10.0,
        stealth_max_domains=2, demotion_streak=2,
    )
    clock = _FakeClock()
    mgr = DomainPolicyManager(config, clock=clock, jitter=lambda lo, hi: lo)

    # First call returns immediately (cadence window starts at 0).
    await mgr.acquire("slow.com")
    state = mgr.get_state("slow.com")
    # After first acquire the scheduled next start should be clock + 0.5s.
    assert state.next_request_at == pytest.approx(clock.now + 0.5, abs=1e-6)


@pytest.mark.asyncio
async def test_cancelled_acquire_releases_reserved_slot() -> None:
    config = PolicyConfig(
        min_delay_sec=1.0,
        max_delay_sec=1.0,
        max_concurrency=2,
        backoff_multiplier=2.0,
        max_backoff_sec=8.0,
        circuit_threshold=3,
        cooldown_sec=60.0,
        stealth_max_domains=2,
        demotion_streak=2,
    )
    clock = _FakeClock()
    mgr = DomainPolicyManager(config, clock=clock, jitter=lambda lo, hi: lo)

    await mgr.acquire("cancelled.com")
    blocked = asyncio.create_task(mgr.acquire("cancelled.com"))
    await asyncio.sleep(0.05)
    blocked.cancel()
    with pytest.raises(asyncio.CancelledError):
        await blocked

    state = mgr.get_state("cancelled.com")
    assert state.in_flight == 1
    assert state.attempts == 1
    await mgr.release("cancelled.com")
