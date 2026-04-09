from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import log_event

logger = logging.getLogger(__name__)

ERR_ZEROBOUNCE_KEY_MISSING = "zerobounce_api_key_missing"
ERR_ZEROBOUNCE_AUTH_FAILED = "zerobounce_auth_failed"
ERR_ZEROBOUNCE_RATE_LIMITED = "zerobounce_rate_limited"
ERR_ZEROBOUNCE_FAILED = "zerobounce_failed"


class ZeroBounceClient:
    def __init__(self) -> None:
        self._api_key = (settings.zerobounce_api_key or "").strip()
        self._base_url = "https://api.zerobounce.net"
        self.last_error_code = ""

    def validate_batch(self, emails: list[str], *, timeout_sec: int = 45) -> tuple[list[dict[str, Any]], str]:
        self.last_error_code = ""
        if not self._api_key:
            self.last_error_code = ERR_ZEROBOUNCE_KEY_MISSING
            return [], self.last_error_code

        payload = {
            "api_key": self._api_key,
            "email_batch": [{"email_address": email} for email in emails],
            "timeout": timeout_sec,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/v2/validatebatch",
                json=payload,
                timeout=timeout_sec + 10,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error_code = ERR_ZEROBOUNCE_FAILED
            log_event(logger, "zerobounce_http_error", error=str(exc))
            return [], self.last_error_code

        if response.status_code in {401, 403}:
            self.last_error_code = ERR_ZEROBOUNCE_AUTH_FAILED
            return [], self.last_error_code
        if response.status_code == 429:
            self.last_error_code = ERR_ZEROBOUNCE_RATE_LIMITED
            return [], self.last_error_code
        if response.status_code >= 400:
            self.last_error_code = ERR_ZEROBOUNCE_FAILED
            log_event(
                logger,
                "zerobounce_non_ok_response",
                status=response.status_code,
                body=response.text[:500],
            )
            return [], self.last_error_code

        try:
            body = response.json()
        except Exception as exc:  # noqa: BLE001
            self.last_error_code = ERR_ZEROBOUNCE_FAILED
            log_event(logger, "zerobounce_invalid_json", error=str(exc), body=response.text[:500])
            return [], self.last_error_code

        if not isinstance(body, list):
            self.last_error_code = ERR_ZEROBOUNCE_FAILED
            log_event(logger, "zerobounce_unexpected_body", body=str(body)[:500])
            return [], self.last_error_code
        return [item for item in body if isinstance(item, dict)], ""
