from __future__ import annotations

import pytest

from app.services import fetch_service
from app.services.fetch_service import FetchResult
from app.services.url_utils import canonical_internal_url, normalize_url, rewrite_to_working_origin


def test_normalize_url_still_coalesces_www_for_job_identity() -> None:
    assert normalize_url("https://www.1proline.com/about") == "https://1proline.com/about"


def test_canonical_internal_url_preserves_working_www_origin() -> None:
    assert (
        canonical_internal_url(
            "https://www.1proline.com/about?ref=nav#team",
            "1proline.com",
        )
        == "https://www.1proline.com/about"
    )


@pytest.mark.asyncio
async def test_fetch_with_fallback_recovers_https_tls_error_via_http(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_static_fetch(url: str, timeout_sec: float = 12.0) -> FetchResult:  # noqa: ARG001
        assert url == "https://1proline.com/"
        return FetchResult(
            final_url=url,
            status_code=0,
            selector=None,
            fetch_mode="static",
            error_code="tls_error",
            error_message="ssl handshake failed",
        )

    async def fake_stealth_fetch_many(urls: list[str], **kwargs) -> list[FetchResult]:  # noqa: ARG001
        assert urls == ["http://1proline.com/"]
        return [
            FetchResult(
                final_url="https://www.1proline.com/",
                status_code=200,
                selector=object(),
                fetch_mode="stealth",
                error_code="",
                error_message="",
            )
        ]

    monkeypatch.setattr(fetch_service, "_static_fetch", fake_static_fetch)
    monkeypatch.setattr(fetch_service, "stealth_fetch_many", fake_stealth_fetch_many)

    result = await fetch_service.fetch_with_fallback("https://1proline.com/")

    assert result.selector is not None
    assert result.fetch_mode == "stealth"
    assert result.final_url == "https://www.1proline.com/"


@pytest.mark.asyncio
async def test_fetch_with_fallback_non_js_skips_tls_browser_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_static_fetch(url: str, timeout_sec: float = 12.0) -> FetchResult:  # noqa: ARG001
        return FetchResult(
            final_url=url,
            status_code=0,
            selector=None,
            fetch_mode="static",
            error_code="tls_error",
            error_message="ssl handshake failed",
        )

    async def fake_impersonate_fetch(url: str, domain: str = "", timeout_sec: float = 15.0) -> FetchResult:  # noqa: ARG001
        return FetchResult(
            final_url=url,
            status_code=0,
            selector=None,
            fetch_mode="impersonate",
            error_code="fetch_failed",
            error_message="impersonate_failed",
        )

    called = False

    async def fake_stealth_fetch_many(urls: list[str], **kwargs) -> list[FetchResult]:  # noqa: ARG001
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(fetch_service, "_static_fetch", fake_static_fetch)
    monkeypatch.setattr(fetch_service, "_impersonate_fetch", fake_impersonate_fetch)
    monkeypatch.setattr(fetch_service, "stealth_fetch_many", fake_stealth_fetch_many)

    result = await fetch_service.fetch_with_fallback("https://1proline.com/", use_js=False)

    assert called is False
    assert result.fetch_mode == "impersonate"
    assert result.error_code == "fetch_failed"


@pytest.mark.asyncio
async def test_fetch_with_fallback_skips_stealth_for_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_static_fetch(url: str, timeout_sec: float = 12.0) -> FetchResult:  # noqa: ARG001
        return FetchResult(
            final_url=url,
            status_code=404,
            selector=None,
            fetch_mode="static",
            error_code="not_found",
            error_message="HTTP 404",
        )

    async def fake_stealth_fetch(url: str, timeout_sec: float):  # noqa: ARG001
        raise AssertionError("stealth fetch should not run for terminal not_found results")

    monkeypatch.setattr(fetch_service, "_static_fetch", fake_static_fetch)
    monkeypatch.setattr(fetch_service, "_stealth_fetch", fake_stealth_fetch)

    result = await fetch_service.fetch_with_fallback("https://example.com/missing", use_js=True)

    assert result.error_code == "not_found"


def test_rewrite_to_working_origin_allows_apex_to_www() -> None:
    assert (
        rewrite_to_working_origin(
            "https://actusa.net/about",
            "https://www.actusa.net/",
            "actusa.net",
        )
        == "https://www.actusa.net/about"
    )


def test_rewrite_to_working_origin_rejects_unrelated_domain() -> None:
    assert (
        rewrite_to_working_origin(
            "https://actuant.com/about",
            "https://www.enerpactoolgroup.com/",
            "actuant.com",
        )
        == ""
    )
