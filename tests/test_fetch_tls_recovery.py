from __future__ import annotations

import pytest

from app.services import fetch_service
from app.services.fetch_service import FetchResult
from app.services.url_utils import canonical_internal_url, normalize_url


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
