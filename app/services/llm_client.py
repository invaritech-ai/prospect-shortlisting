"""Centralized OpenRouter LLM client.

All LLM call sites in the application go through this module:
  - classify_links_with_llm  (page-kind URL classification)
  - MarkdownService          (LLM-fallback markdown conversion)
  - AnalysisService          (prospect classification)
  - LeadershipService        (coming soon)
  - SnovService              (coming soon)

Features
--------
- Single SSL context shared across all calls
- Retry with exponential backoff on 429 (rate limit) and 5xx (server errors)
- Optional per-instance minimum interval between calls (per-process throttle)
- Structured logging: model, purpose, latency, token usage on every call
- Typed error codes — callers match against ERR_* constants, not strings

Usage
-----
    from app.services.llm_client import LLMClient, ERR_RATE_LIMITED

    client = LLMClient(purpose="classify_links")
    content, error = client.chat(
        model="mistralai/mistral-small-2603",
        messages=[{"role": "user", "content": "..."}],
        response_format={"type": "json_object"},
    )
    if error:
        ...  # handle
"""
from __future__ import annotations

import json
import logging
import ssl
import time
import traceback
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.core.logging import log_event
from app.services import credentials_resolver

logger = logging.getLogger(__name__)

# Shared SSL context — created once, reused for all calls.
_SSL_CTX = ssl.create_default_context()

# ── Error codes ───────────────────────────────────────────────────────────────
ERR_API_KEY_MISSING  = "llm_api_key_missing"   # no key configured
ERR_RATE_LIMITED     = "llm_rate_limited"       # 429 exhausted all retries
ERR_TIMEOUT          = "llm_timeout"            # urllib timeout
ERR_EMPTY_RESPONSE   = "llm_empty_response"     # 200 OK but no choices
ERR_SERVER_ERROR     = "llm_server_error"       # 5xx exhausted all retries
ERR_FAILED           = "llm_failed"             # any other error


class LLMClient:
    """Thread-safe OpenRouter chat-completions client.

    Parameters
    ----------
    purpose:
        Short label included in every log event (e.g. "classify_links",
        "markdown", "analysis"). Makes log queries easy.
    max_retries:
        How many times to retry on 429 or 5xx before giving up.
        Default 3 (attempts = max_retries + 1).
    backoff_base_sec / backoff_factor:
        Exponential backoff: delay = base * factor^attempt.
        Defaults give 2s, 8s, 32s.
    min_interval_sec:
        Minimum gap between successive calls within this process.
        0.0 (default) = no throttle. Set to 0.5 for high-volume callers.
    default_timeout:
        Per-call HTTP timeout in seconds. Can be overridden per-call.
    """

    def __init__(
        self,
        *,
        purpose: str = "",
        max_retries: int = 3,
        backoff_base_sec: float = 2.0,
        backoff_factor: float = 4.0,
        min_interval_sec: float = 0.0,
        default_timeout: int = 120,
    ) -> None:
        self._api_key = ""
        self._base_url = settings.openrouter_base_url.rstrip("/")
        self._purpose = purpose
        self._max_retries = max_retries
        self._backoff_base = backoff_base_sec
        self._backoff_factor = backoff_factor
        self._min_interval = min_interval_sec
        self._default_timeout = default_timeout
        self._last_call_at: float = 0.0  # monotonic; per-instance throttle

    def _resolved_api_key(self) -> str:
        return credentials_resolver.resolve("openrouter", "api_key") or (self._api_key or "").strip()

    def chat_with_usage(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        response_format: dict | None = None,
        timeout: int | None = None,
    ) -> tuple[str, str, dict]:
        """Send a chat completion. Returns ``(content, error_code, usage_meta)``.

        ``error_code`` is ``""`` on success, an ``ERR_*`` constant on failure.
        On failure ``content`` is always ``""``.
        """
        usage_meta: dict = {
            "provider": "openrouter",
            "model": model,
            "request_id": None,
            "openrouter_generation_id": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "billed_cost_usd": None,
            "raw_usage": None,
        }
        api_key = self._resolved_api_key()
        if not api_key:
            log_event(logger, "llm_api_key_missing", purpose=self._purpose, model=model)
            return "", ERR_API_KEY_MISSING, usage_meta

        # Per-instance throttle
        if self._min_interval > 0:
            gap = time.monotonic() - self._last_call_at
            if gap < self._min_interval:
                time.sleep(self._min_interval - gap)

        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        effective_timeout = timeout if timeout is not None else self._default_timeout
        last_exc: Exception | None = None
        t_start = time.monotonic()

        for attempt in range(self._max_retries + 1):
            req = Request(
                url=f"{self._base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": settings.openrouter_site_url,
                    "X-Title": settings.openrouter_app_name,
                },
            )
            try:
                with urlopen(req, context=_SSL_CTX, timeout=effective_timeout) as resp:  # noqa: S310
                    raw = resp.read().decode("utf-8", errors="ignore")
                    response_headers = dict(resp.headers.items()) if getattr(resp, "headers", None) else {}

                self._last_call_at = time.monotonic()
                latency_ms = int((self._last_call_at - t_start) * 1000)

                decoded = json.loads(raw)
                choices = decoded.get("choices") or []
                if not choices:
                    log_event(logger, "llm_empty_choices",
                              model=model, purpose=self._purpose, latency_ms=latency_ms)
                    return "", ERR_EMPTY_RESPONSE, usage_meta

                content = choices[0]["message"]["content"]
                if isinstance(content, list):
                    # Some models return [{type: "text", text: "..."}, ...]
                    content = "\n".join(
                        str(item.get("text", ""))
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    )
                content = str(content or "").strip()

                usage = decoded.get("usage") or {}
                usage_meta["request_id"] = (
                    response_headers.get("x-request-id")
                    or response_headers.get("X-Request-Id")
                    or decoded.get("id")
                )
                usage_meta["openrouter_generation_id"] = (
                    usage.get("generation_id")
                    or response_headers.get("x-openrouter-generation-id")
                    or response_headers.get("X-Openrouter-Generation-Id")
                    or decoded.get("openrouter_generation_id")
                    or decoded.get("generation_id")
                )
                usage_meta["prompt_tokens"] = int(usage.get("prompt_tokens") or 0)
                usage_meta["completion_tokens"] = int(usage.get("completion_tokens") or 0)
                usage_meta["billed_cost_usd"] = (
                    usage.get("cost")
                    or usage.get("total_cost")
                    or decoded.get("cost")
                    or decoded.get("billed_cost_usd")
                )
                usage_meta["raw_usage"] = usage or None
                log_event(
                    logger, "llm_call_ok",
                    model=model, purpose=self._purpose, latency_ms=latency_ms,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                )
                return content, "", usage_meta

            except HTTPError as exc:
                last_exc = exc
                is_429 = exc.code == 429
                is_5xx = exc.code >= 500

                if (is_429 or is_5xx) and attempt < self._max_retries:
                    if is_429:
                        retry_after = exc.headers.get("Retry-After") if exc.headers else None
                        delay = float(retry_after) if (retry_after and str(retry_after).isdigit()) \
                            else self._backoff_base * (self._backoff_factor ** attempt)
                        log_event(logger, "llm_429_retry", model=model, purpose=self._purpose,
                                  attempt=attempt + 1, delay_sec=round(delay, 1))
                    else:
                        delay = self._backoff_base * (self._backoff_factor ** attempt)
                        log_event(logger, "llm_5xx_retry", model=model, purpose=self._purpose,
                                  status=exc.code, attempt=attempt + 1, delay_sec=round(delay, 1))
                    time.sleep(delay)
                    continue

                if is_429:
                    log_event(logger, "llm_429_exhausted", model=model, purpose=self._purpose,
                              error=str(exc), attempts=attempt + 1)
                    return "", ERR_RATE_LIMITED, usage_meta
                if is_5xx:
                    log_event(logger, "llm_5xx_exhausted", model=model, purpose=self._purpose,
                              status=exc.code, error=str(exc), attempts=attempt + 1)
                    return "", ERR_SERVER_ERROR, usage_meta

                log_event(logger, "llm_http_error", model=model, purpose=self._purpose,
                          status=exc.code, error=str(exc))
                return "", ERR_FAILED, usage_meta

            except TimeoutError:
                log_event(logger, "llm_timeout", model=model, purpose=self._purpose,
                          timeout_sec=effective_timeout)
                return "", ERR_TIMEOUT, usage_meta

            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log_event(logger, "llm_error", model=model, purpose=self._purpose,
                          error=str(exc), traceback=traceback.format_exc())
                return "", ERR_FAILED, usage_meta

        log_event(logger, "llm_retries_exhausted", model=model, purpose=self._purpose,
                  error=str(last_exc), attempts=self._max_retries + 1)
        return "", ERR_FAILED, usage_meta

    def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        response_format: dict | None = None,
        timeout: int | None = None,
    ) -> tuple[str, str]:
        """Backward-compatible wrapper returning ``(content, error_code)`` only."""
        content, error, _ = self.chat_with_usage(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
            timeout=timeout,
        )
        return content, error
