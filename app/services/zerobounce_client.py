from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.logging import log_event
from app.services import credentials_resolver

logger = logging.getLogger(__name__)

ERR_ZEROBOUNCE_KEY_MISSING = "zerobounce_api_key_missing"
ERR_ZEROBOUNCE_AUTH_FAILED = "zerobounce_auth_failed"
ERR_ZEROBOUNCE_RATE_LIMITED = "zerobounce_rate_limited"
ERR_ZEROBOUNCE_FAILED = "zerobounce_failed"


class ZeroBounceClient:
    def __init__(self) -> None:
        self._api_key = ""
        self._base_url = "https://api.zerobounce.net"
        self.last_error_code = ""

    def _resolve_api_key(self) -> str:
        return credentials_resolver.resolve("zerobounce", "api_key") or (self._api_key or "").strip()

    def check_credentials(self) -> tuple[bool, str, str]:
        api_key = self._resolve_api_key()
        if not api_key:
            return False, ERR_ZEROBOUNCE_KEY_MISSING, "ZeroBounce API key is missing."
        try:
            response = httpx.get(
                f"{self._base_url}/v2/getcredits",
                params={"api_key": api_key},
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "zerobounce_credential_check_http_error", error=str(exc))
            return False, ERR_ZEROBOUNCE_FAILED, "ZeroBounce credential check failed."
        if response.status_code in {401, 403}:
            return False, ERR_ZEROBOUNCE_AUTH_FAILED, "ZeroBounce rejected the API key."
        if response.status_code >= 400:
            return False, ERR_ZEROBOUNCE_FAILED, f"ZeroBounce returned HTTP {response.status_code}."
        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            return False, ERR_ZEROBOUNCE_FAILED, "ZeroBounce returned invalid JSON."
        credits = body.get("Credits") if isinstance(body, dict) else None
        if credits == -1:
            return False, ERR_ZEROBOUNCE_AUTH_FAILED, "ZeroBounce rejected the API key."
        return True, "", "ZeroBounce credentials are valid."

    def validate_batch(self, emails: list[str], *, timeout_sec: int = 45) -> tuple[list[dict[str, Any]], str]:
        self.last_error_code = ""
        api_key = self._resolve_api_key()
        if not api_key:
            self.last_error_code = ERR_ZEROBOUNCE_KEY_MISSING
            return [], self.last_error_code

        payload = {
            "api_key": api_key,
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

        if isinstance(body, dict):
            email_batch = body.get("email_batch")
            errors = body.get("errors")
            usable_errors = [item for item in errors if isinstance(item, dict)] if isinstance(errors, list) else []
            if usable_errors:
                if any(self._is_auth_or_credit_error(error) for error in usable_errors):
                    self.last_error_code = ERR_ZEROBOUNCE_AUTH_FAILED
                    log_event(
                        logger,
                        "zerobounce_auth_or_credits_error",
                        body=str(body)[:500],
                    )
                    return [], self.last_error_code
            if not isinstance(email_batch, list):
                self.last_error_code = ERR_ZEROBOUNCE_FAILED
                log_event(
                    logger,
                    "zerobounce_malformed_batch_envelope",
                    body=str(body)[:500],
                )
                return [], self.last_error_code
            results = [item for item in email_batch if isinstance(item, dict)]
            if usable_errors:
                if not results:
                    self.last_error_code = ERR_ZEROBOUNCE_FAILED
                    log_event(
                        logger,
                        "zerobounce_batch_errors",
                        body=str(body)[:500],
                    )
                    return [], self.last_error_code
            return results, ""
        if not isinstance(body, list):
            self.last_error_code = ERR_ZEROBOUNCE_FAILED
            log_event(logger, "zerobounce_unexpected_body", body=str(body)[:500])
            return [], self.last_error_code
        return [item for item in body if isinstance(item, dict)], ""

    def _is_auth_or_credit_error(self, error: dict[str, Any]) -> bool:
        error_text = str(error.get("error") or "").lower()
        return "invalid api key" in error_text or "credits" in error_text
