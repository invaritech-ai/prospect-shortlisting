"""Optional live fetch checks against a handful of real domains.

Set `PS_SCRAPE_LIVE_BENCHMARK=1` (or `SCRAPE_LIVE_BENCHMARK=1`) to enable.
Skipped by default so CI and offline runs stay fast.

These complement `scripts/benchmark_fetch_domains.py` for human-friendly tables.
"""
from __future__ import annotations

import os

import pytest

from app.core.config import settings
from app.services.fetch_service import FetchErrorCode, _impersonate_fetch, _static_fetch

pytestmark = pytest.mark.asyncio


def _live_enabled() -> bool:
    return (
        os.environ.get("PS_SCRAPE_LIVE_BENCHMARK", "").strip() == "1"
        or os.environ.get("SCRAPE_LIVE_BENCHMARK", "").strip() == "1"
    )


skip_offline = pytest.mark.skipif(
    not _live_enabled(),
    reason="Set PS_SCRAPE_LIVE_BENCHMARK=1 to run live domain fetch tests",
)


@skip_offline
@pytest.mark.parametrize(
    "url,domain_hint",
    [
        ("https://example.com/", "example.com"),
        ("http://2t.com/", "2t.com"),
        ("https://21stcenturybearings.com/", "21stcenturybearings.com"),
    ],
)
async def test_static_or_impersonate_succeeds(url: str, domain_hint: str) -> None:
    """At least one of static or impersonate should return a selector for these known-good URLs."""
    static = await _static_fetch(url, timeout_sec=settings.scrape_static_timeout_sec)
    imp = await _impersonate_fetch(
        url, domain=domain_hint, timeout_sec=settings.scrape_impersonate_timeout_sec
    )
    assert static.selector is not None or imp.selector is not None, (
        f"both tiers failed url={url} static_err={static.error_code!r} imp_err={imp.error_code!r}"
    )


@skip_offline
async def test_example_com_static_clean() -> None:
    """Control URL should succeed on static tier without escalation."""
    r = await _static_fetch("https://example.com/", timeout_sec=settings.scrape_static_timeout_sec)
    assert r.selector is not None
    assert r.error_code in (FetchErrorCode.OK, "")
