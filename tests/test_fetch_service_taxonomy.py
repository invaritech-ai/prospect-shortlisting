"""Unit tests for the unified fetch error taxonomy + Phase-1 fixes.

Covers:
  * Deterministic mapping from transport errors + HTTP status -> canonical codes.
  * `_classify_html_response` detecting bot-wall / too-thin / parse failures.
  * `_static_fetch` regression fix (brotli / parser resilience).
"""
from __future__ import annotations

import asyncio
import httpx
import pytest

from app.services import fetch_service
from app.services.fetch_service import (
    ESCALATABLE_ERROR_CODES,
    FetchErrorCode,
    _classify_html_response,
    _static_fetch,
    classify_fetch_error,
    classify_http_status,
)


def test_classify_fetch_error_maps_transport_messages() -> None:
    assert classify_fetch_error("ssl handshake failed") == FetchErrorCode.TLS_ERROR
    assert classify_fetch_error("Read timed out") == FetchErrorCode.TIMEOUT
    assert classify_fetch_error("could not resolve host") == FetchErrorCode.DNS_NOT_RESOLVED
    assert classify_fetch_error("non_html response") == FetchErrorCode.NON_HTML
    assert classify_fetch_error("kaboom") == FetchErrorCode.FETCH_FAILED


def test_classify_http_status_maps_well_known_codes() -> None:
    assert classify_http_status(200) == FetchErrorCode.OK
    assert classify_http_status(403) == FetchErrorCode.ACCESS_DENIED
    assert classify_http_status(404) == FetchErrorCode.NOT_FOUND
    assert classify_http_status(429) == FetchErrorCode.RATE_LIMITED
    assert classify_http_status(503) == FetchErrorCode.FETCH_FAILED


def test_classify_html_response_detects_bot_wall() -> None:
    html = "<html><body>Checking your browser before accessing...</body></html>"
    result = _classify_html_response(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        html_text=html,
        fetch_mode="static",
    )
    assert result.selector is None
    assert result.error_code == FetchErrorCode.BOT_PROTECTION


def test_classify_html_response_detects_too_thin() -> None:
    result = _classify_html_response(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        html_text="<html><body>Hi.</body></html>",
        fetch_mode="static",
    )
    assert result.selector is None
    assert result.error_code == FetchErrorCode.TOO_THIN


def test_classify_html_response_detects_parked_domain() -> None:
    result = _classify_html_response(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        html_text="<html><body>This domain is for sale. Buy this domain today.</body></html>",
        fetch_mode="static",
    )
    assert result.selector is None
    assert result.error_code == FetchErrorCode.PARKED_DOMAIN


def test_classify_html_response_success_returns_selector() -> None:
    body = (
        "<html><head><title>T</title></head><body>"
        + ("<p>Real content about this company and its offerings.</p>" * 20)
        + "</body></html>"
    )
    result = _classify_html_response(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        html_text=body,
        fetch_mode="static",
    )
    assert result.error_code == FetchErrorCode.OK
    assert result.selector is not None


def test_classify_html_response_http_error_uses_status_taxonomy() -> None:
    result = _classify_html_response(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=404,
        html_text="<html></html>",
        fetch_mode="static",
    )
    assert result.error_code == FetchErrorCode.NOT_FOUND


def test_escalatable_codes_include_policy_relevant_errors() -> None:
    for code in (
        FetchErrorCode.BOT_PROTECTION,
        FetchErrorCode.ACCESS_DENIED,
        FetchErrorCode.RATE_LIMITED,
        FetchErrorCode.TOO_THIN,
        FetchErrorCode.TIMEOUT,
        FetchErrorCode.FETCH_FAILED,
        FetchErrorCode.PARSER_ERROR,
    ):
        assert code in ESCALATABLE_ERROR_CODES


@pytest.mark.asyncio
async def test_static_fetch_handles_good_html(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (
        "<html><head><title>T</title></head><body>"
        + ("<p>Quality body content for the classifier.</p>" * 20)
        + "</body></html>"
    )

    class _FakeResp:
        def __init__(self) -> None:
            self.status_code = 200
            self.text = body
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self.url = "https://example.com/"

    class _FakeClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):  # noqa: ARG002
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    result = await _static_fetch("https://example.com/")
    assert result.error_code == FetchErrorCode.OK
    assert result.selector is not None
    assert result.fetch_mode == "static"


@pytest.mark.asyncio
async def test_static_fetch_flags_parser_error_when_text_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: brotli-encoded body decoded into gibberish should surface as parser_error,
    not masquerade as a successful fetch."""

    class _FakeResp:
        def __init__(self) -> None:
            self.status_code = 200
            # Intentionally large enough to pass too-thin but non-HTML garbage
            # bytes (simulates what happened with undecoded brotli payload).
            self.text = "x" * 400
            self.headers = {"content-type": "text/html"}
            self.url = "https://example.com/"

    class _FakeClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):  # noqa: ARG002
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    # Force the Selector builder to raise so we validate parser_error branch.
    def _boom(*_, **__):
        raise RuntimeError("Selector class needs HTML content, or root arguments to work")

    monkeypatch.setattr(fetch_service, "Selector", _boom)

    result = await _static_fetch("https://example.com/")
    assert result.error_code == FetchErrorCode.PARSER_ERROR
    assert result.selector is None


@pytest.mark.asyncio
async def test_static_fetch_non_html_404_preserves_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResp:
        def __init__(self) -> None:
            self.status_code = 404
            self.text = "not found"
            self.headers = {"content-type": "application/json"}
            self.url = "https://example.com/missing"

    class _FakeClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):  # noqa: ARG002
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    result = await _static_fetch("https://example.com/missing")
    assert result.error_code == FetchErrorCode.NOT_FOUND
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_impersonate_fetch_non_html_403_preserves_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResp:
        def __init__(self) -> None:
            self.status_code = 403
            self.text = '{"detail":"forbidden"}'
            self.headers = {"content-type": "application/json"}
            self.url = "https://example.com/blocked"

    class _FakeSession:
        def get(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return _FakeResp()

    async def _fake_get_session(domain: str):  # noqa: ARG001
        return _FakeSession()

    async def _fake_get_lock(domain: str):  # noqa: ARG001
        return asyncio.Lock()

    monkeypatch.setattr(fetch_service, "_CURL_AVAILABLE", True)
    monkeypatch.setattr(fetch_service, "_get_impersonate_session", _fake_get_session)
    monkeypatch.setattr(fetch_service, "_get_impersonate_request_lock", _fake_get_lock)

    result = await fetch_service._impersonate_fetch("https://example.com/blocked", domain="example.com")
    assert result.error_code == FetchErrorCode.ACCESS_DENIED
    assert result.status_code == 403


def test_static_headers_do_not_advertise_unsupported_brotli() -> None:
    # See module docstring: advertising `br` without the `brotli` package
    # causes httpx to return undecoded bytes and breaks Selector construction.
    encoding = fetch_service._STATIC_HEADERS["Accept-Encoding"]
    assert "br" not in encoding
    assert "gzip" in encoding


def test_stealth_session_kwargs_are_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_service.settings, "browserless_url", "wss://example.invalid/stealth", raising=False)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_max_pages", 2)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_block_images", True)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_disable_resources", True)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_humanize", True)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_os_randomize", True)
    monkeypatch.setattr(fetch_service.settings, "scrape_proxy_url", "")

    kwargs = fetch_service._stealth_session_kwargs()

    assert "cdp_url" not in kwargs
    assert kwargs["max_pages"] == 2
    assert kwargs["block_images"] is True
    assert kwargs["disable_resources"] is True
    assert kwargs["humanize"] is True
    assert kwargs["os_randomize"] is True
    assert "proxy" not in kwargs

    monkeypatch.setattr(fetch_service.settings, "scrape_proxy_url", "http://proxy.example.com:8080")
    kwargs_with_proxy = fetch_service._stealth_session_kwargs()
    assert kwargs_with_proxy.get("proxy") == "http://proxy.example.com:8080"
