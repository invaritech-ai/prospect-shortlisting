from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.services import credentials_resolver
from app.services.zerobounce_client import (
    ERR_ZEROBOUNCE_AUTH_FAILED,
    ZeroBounceClient,
)


class _FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


def test_validate_batch_accepts_documented_success_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(credentials_resolver, "resolve", lambda provider, field: "api-key")

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            {
                "email_batch": [
                    {
                        "address": "valid@example.com",
                        "status": "valid",
                        "sub_status": "",
                    }
                ],
                "errors": [],
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    results, error_code = ZeroBounceClient().validate_batch(["valid@example.com"])

    assert error_code == ""
    assert results == [
        {
            "address": "valid@example.com",
            "status": "valid",
            "sub_status": "",
        }
    ]


def test_validate_batch_maps_documented_auth_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(credentials_resolver, "resolve", lambda provider, field: "api-key")

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            {
                "email_batch": [],
                "errors": [
                    {
                        "error": "Invalid API Key or your account ran out of credits",
                        "email_address": "all",
                    }
                ],
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    results, error_code = ZeroBounceClient().validate_batch(["valid@example.com"])

    assert results == []
    assert error_code == ERR_ZEROBOUNCE_AUTH_FAILED


def test_validate_batch_keeps_usable_rows_with_nonfatal_row_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(credentials_resolver, "resolve", lambda provider, field: "api-key")

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            {
                "email_batch": [
                    {
                        "address": "valid@example.com",
                        "status": "valid",
                    }
                ],
                "errors": [
                    {
                        "error": "Invalid email format",
                        "email_address": "bad-input",
                    }
                ],
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    results, error_code = ZeroBounceClient().validate_batch(["valid@example.com", "bad-input"])

    assert error_code == ""
    assert results == [
        {
            "address": "valid@example.com",
            "status": "valid",
        }
    ]
