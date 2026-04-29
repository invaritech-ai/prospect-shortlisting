"""Snov.io API client: OAuth token management, domain prospect search, email lookup.

API pattern: start a task → poll for result (async, task-hash based).
Rate limit: 60 req/min → min_interval_sec=1.0.
Auth: OAuth2 client_credentials, tokens expire in ~1 hour.

Usage
-----
    from app.services.snov_client import SnovClient, ERR_SNOV_CREDENTIALS_MISSING

    client = SnovClient()
    count, err = client.get_domain_email_count("example.com")
    prospects, total, err = client.search_prospects("example.com")
    emails, err = client.search_prospect_email(prospect_hash)
    emails, err = client.find_email_by_name("John", "Smith", "example.com")
"""
from __future__ import annotations

import hashlib
import json
import logging
import ssl
import time
import traceback
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.logging import log_event
from app.services import credentials_resolver
def get_redis():
    return None

logger = logging.getLogger(__name__)

_SNOV_BASE = "https://api.snov.io"
_SSL_CTX = ssl.create_default_context()

# ── Error codes ───────────────────────────────────────────────────────────────
ERR_SNOV_CREDENTIALS_MISSING = "snov_credentials_missing"
ERR_SNOV_AUTH_FAILED         = "snov_auth_failed"
ERR_SNOV_RATE_LIMITED        = "snov_rate_limited"
ERR_SNOV_TIMEOUT             = "snov_timeout"
ERR_SNOV_FAILED              = "snov_failed"

# ── In-memory token fallback (per-process) ────────────────────────────────────
_mem_token: str = ""
_mem_token_expires_at: float = 0.0  # monotonic
_mem_token_cache_key: str = ""


_REDIS_TOKEN_KEY = "snov:access_token"


def _credential_cache_key(client_id: str, client_secret: str) -> str:
    digest = hashlib.sha256(f"{client_id}\0{client_secret}".encode("utf-8")).hexdigest()[:24]
    return f"{_REDIS_TOKEN_KEY}:{digest}"


def reset_token_cache() -> None:
    global _mem_token, _mem_token_expires_at, _mem_token_cache_key  # noqa: PLW0603
    _mem_token = ""
    _mem_token_expires_at = 0.0
    _mem_token_cache_key = ""


def clear_cached_access_tokens() -> None:
    reset_token_cache()
    redis = get_redis()
    if not redis:
        return
    try:
        for key in redis.scan_iter(match=f"{_REDIS_TOKEN_KEY}*"):
            redis.delete(key)
    except Exception:  # noqa: BLE001
        pass


class SnovClient:
    """Snov.io API client.

    Parameters
    ----------
    max_retries:
        Retry on 429 / 5xx before giving up.
    poll_interval_sec:
        Initial gap between task-result polls.
    poll_max_attempts:
        Max polling attempts before declaring a task failed.
    min_interval_sec:
        Minimum gap between HTTP calls (60 req/min → 1.0 s).
    default_timeout:
        HTTP timeout per call in seconds.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        poll_interval_sec: float = 2.0,
        poll_max_attempts: int = 15,
        min_interval_sec: float = 1.0,
        default_timeout: int = 30,
    ) -> None:
        self._client_id = ""
        self._client_secret = ""
        self._max_retries = max_retries
        self._poll_interval = poll_interval_sec
        self._poll_max_attempts = poll_max_attempts
        self._min_interval = min_interval_sec
        self._default_timeout = default_timeout
        self._last_call_at: float = 0.0

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call_at
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)

    def _post(self, path: str, payload: dict, timeout: int | None = None, bearer: str = "") -> tuple[dict, str]:
        """POST JSON to Snov API. Returns (data_dict, error_code)."""
        self._throttle()
        url = f"{_SNOV_BASE}{path}"
        data = json.dumps(payload).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        req = Request(url, data=data, method="POST", headers=headers)
        return self._do_request(req, timeout or self._default_timeout)

    def _get(self, path: str, timeout: int | None = None, bearer: str = "") -> tuple[dict, str]:
        """GET from Snov API. Returns (data_dict, error_code)."""
        self._throttle()
        url = f"{_SNOV_BASE}{path}"
        headers: dict[str, str] = {}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        req = Request(url, method="GET", headers=headers)
        return self._do_request(req, timeout or self._default_timeout)

    def _do_request(self, req: Request, timeout: int) -> tuple[dict, str]:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with urlopen(req, context=_SSL_CTX, timeout=timeout) as resp:  # noqa: S310
                    raw = resp.read().decode("utf-8", errors="ignore")
                self._last_call_at = time.monotonic()
                return json.loads(raw), ""
            except HTTPError as exc:
                last_exc = exc
                if exc.code == 429 and attempt < self._max_retries:
                    delay = 2.0 * (2 ** attempt)
                    log_event(logger, "snov_429_retry", attempt=attempt + 1, delay_sec=delay)
                    time.sleep(delay)
                    continue
                if exc.code >= 500 and attempt < self._max_retries:
                    delay = 2.0 * (2 ** attempt)
                    log_event(logger, "snov_5xx_retry", status=exc.code, attempt=attempt + 1, delay_sec=delay)
                    time.sleep(delay)
                    continue
                if exc.code == 429:
                    return {}, ERR_SNOV_RATE_LIMITED
                if exc.code in (401, 403):
                    return {}, ERR_SNOV_AUTH_FAILED
                log_event(logger, "snov_http_error", status=exc.code, error=str(exc))
                return {}, ERR_SNOV_FAILED
            except TimeoutError:
                log_event(logger, "snov_timeout", url=req.full_url)
                return {}, ERR_SNOV_TIMEOUT
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log_event(logger, "snov_error", error=str(exc), traceback=traceback.format_exc())
                return {}, ERR_SNOV_FAILED
        log_event(logger, "snov_retries_exhausted", error=str(last_exc))
        return {}, ERR_SNOV_FAILED

    # ── OAuth token ───────────────────────────────────────────────────────────

    def _get_access_token(self, *, force_refresh: bool = False) -> tuple[str, str]:
        """Return (access_token, error_code). Token cached in Redis → in-memory."""
        global _mem_token, _mem_token_expires_at, _mem_token_cache_key  # noqa: PLW0603

        client_id = credentials_resolver.resolve("snov", "client_id") or (self._client_id or "").strip()
        client_secret = credentials_resolver.resolve("snov", "client_secret") or (self._client_secret or "").strip()
        if not client_id or not client_secret:
            return "", ERR_SNOV_CREDENTIALS_MISSING

        cache_key = _credential_cache_key(client_id, client_secret)

        # 1. Try Redis cache
        redis = get_redis()
        if redis and not force_refresh:
            try:
                cached = redis.get(cache_key)
                if cached:
                    return cached.decode("utf-8"), ""
            except Exception:  # noqa: BLE001
                pass

        # 2. Try in-memory cache (per-process fallback)
        if (
            not force_refresh
            and _mem_token
            and _mem_token_cache_key == cache_key
            and time.monotonic() < _mem_token_expires_at
        ):
            return _mem_token, ""

        # 3. Fetch new token
        self._throttle()
        url = f"{_SNOV_BASE}/v1/oauth/access_token"
        payload = urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode("utf-8")
        req = Request(url, data=payload, method="POST",
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(req, context=_SSL_CTX, timeout=self._default_timeout) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8", errors="ignore")
            self._last_call_at = time.monotonic()
        except HTTPError as exc:
            log_event(logger, "snov_auth_failed", status=exc.code, error=str(exc))
            return "", ERR_SNOV_AUTH_FAILED
        except TimeoutError:
            return "", ERR_SNOV_TIMEOUT
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "snov_auth_error", error=str(exc))
            return "", ERR_SNOV_FAILED

        try:
            data = json.loads(raw)
            token = str(data.get("access_token") or "")
            expires_in = int(data.get("expires_in") or 3600)
        except Exception:  # noqa: BLE001
            return "", ERR_SNOV_AUTH_FAILED

        if not token:
            return "", ERR_SNOV_AUTH_FAILED

        ttl = max(expires_in - 60, 60)

        # Cache in Redis
        if redis:
            try:
                redis.setex(cache_key, ttl, token)
            except Exception:  # noqa: BLE001
                pass

        # Cache in memory
        _mem_token = token
        _mem_token_expires_at = time.monotonic() + ttl
        _mem_token_cache_key = cache_key

        log_event(logger, "snov_token_refreshed", expires_in=expires_in)
        return token, ""

    # ── Task polling ──────────────────────────────────────────────────────────

    def _poll_task(self, result_path: str, bearer: str = "") -> tuple[dict, str]:
        """Poll a Snov task result endpoint until status != 'in_progress'."""
        interval = self._poll_interval
        for attempt in range(self._poll_max_attempts):
            if attempt > 0:
                time.sleep(interval)
                interval = min(interval * 1.5, 10.0)
            data, err = self._get(result_path, bearer=bearer)
            if err:
                return {}, err
            status = str(data.get("status") or "").lower()
            if status in ("done", "complete", "completed", "success"):
                return data, ""
            if status in ("failed", "error"):
                log_event(logger, "snov_task_failed", path=result_path, data=data)
                return {}, ERR_SNOV_FAILED
            # still "in_progress" or similar — keep polling
        log_event(logger, "snov_task_timeout", path=result_path, attempts=self._poll_max_attempts)
        return {}, ERR_SNOV_TIMEOUT

    # ── Public API ────────────────────────────────────────────────────────────

    def get_balance(self) -> tuple[int | None, str]:
        """Return (credits_remaining, error_code). credits=None on error.

        Uses GET /v1/get-balance?access_token=TOKEN.
        Response: {"success": true, "data": {"balance": "25000.00", ...}}
        """
        token, err = self._get_access_token()
        if err:
            return None, err
        data, err = self._get(f"/v1/get-balance?access_token={token}")
        if err:
            return None, err
        raw = (data.get("data") or {}).get("balance")
        try:
            return (int(float(raw)) if raw is not None else None), ""
        except (TypeError, ValueError):
            return None, ""

    def get_domain_email_count(self, domain: str) -> tuple[int, str]:
        """Free check: how many emails Snov has for this domain.

        Returns (count, error_code). count=0 on error.
        """
        token, err = self._get_access_token()
        if err:
            return 0, err
        data, err = self._post("/v1/get-domain-emails-count", {
            "access_token": token,
            "domain": domain,
        })
        if err:
            return 0, err
        count = int(data.get("result") or data.get("count") or 0)
        return count, ""

    def search_prospects(self, domain: str, page: int = 1) -> tuple[list[dict], int, str]:
        """Start a domain prospect search and poll for results.

        Returns (prospects_list, total_count, error_code).
        Each prospect has: first_name, last_name, position, source_page, search_emails_start.
        """
        token, err = self._get_access_token()
        if err:
            return [], 0, err

        start_data, err = self._post("/v2/domain-search/prospects/start", {
            "domain": domain,
            "page": page,
        }, bearer=token)
        if err:
            return [], 0, err

        task_hash = str((start_data.get("meta") or {}).get("task_hash") or "")
        if not task_hash:
            log_event(logger, "snov_no_task_hash", domain=domain, data=start_data)
            return [], 0, ERR_SNOV_FAILED

        result, err = self._poll_task(f"/v2/domain-search/prospects/result/{task_hash}", bearer=token)
        if err:
            return [], 0, err

        prospects = result.get("data") or []
        total = int((result.get("meta") or {}).get("total_count") or len(prospects))

        log_event(logger, "snov_prospects_found", domain=domain, page=page,
                  prospects=len(prospects), total=total)
        return prospects, total, ""

    def search_prospect_email(self, prospect_hash: str) -> tuple[list[dict], str]:
        """Find email addresses for a specific prospect by their Snov hash.

        Returns (emails_list, error_code).
        Each email dict has: email, smtp_status.
        Consumes 1 credit only if an email is found.
        """
        token, err = self._get_access_token()
        if err:
            return [], err

        # Correct path: /v2/domain-search/prospects/search-emails/start/{prospect_hash}
        start_data, err = self._post(
            f"/v2/domain-search/prospects/search-emails/start/{prospect_hash}",
            {},
            bearer=token,
        )
        if err:
            return [], err

        task_hash = str((start_data.get("meta") or {}).get("task_hash") or "")
        if not task_hash:
            log_event(logger, "snov_no_email_task_hash", prospect_hash=prospect_hash, data=start_data)
            return [], ERR_SNOV_FAILED

        result, err = self._poll_task(
            f"/v2/domain-search/prospects/search-emails/result/{task_hash}",
            bearer=token,
        )
        if err:
            return [], err

        # result.data.emails — docs: {"data": {"emails": [{"email": "...", "smtp_status": "valid"}]}}
        data = result.get("data") or {}
        emails = data.get("emails") if isinstance(data, dict) else []
        return list(emails or []), ""

    def find_email_by_name(self, first_name: str, last_name: str, domain: str) -> tuple[list[dict], str]:
        """Find email by first name + last name + domain (pattern-based guess).

        Uses /v2/emails-by-domain-by-name/start — costs 1 credit per email
        found with valid/unknown status.  Returns (emails_list, error_code).
        Each email dict has: email, smtp_status, is_valid_format, etc.
        """
        token, err = self._get_access_token()
        if err:
            return [], err

        start_data, err = self._post("/v2/emails-by-domain-by-name/start", {
            "rows": [{"first_name": first_name, "last_name": last_name, "domain": domain}],
        }, bearer=token)
        if err:
            return [], err

        task_hash = str((start_data.get("meta") or {}).get("task_hash") or "")
        if not task_hash:
            log_event(logger, "snov_no_email_finder_hash",
                      first_name=first_name, last_name=last_name, domain=domain, data=start_data)
            return [], ERR_SNOV_FAILED

        result, err = self._poll_task(
            f"/v2/emails-by-domain-by-name/result?task_hash={task_hash}",
            bearer=token,
        )
        if err:
            return [], err

        # Response: {"data": [{"emails": [{"email": "...", "smtp_status": "valid", ...}]}]}
        rows = result.get("data") or []
        if rows and isinstance(rows, list) and isinstance(rows[0], dict):
            emails = rows[0].get("emails") or []
            return list(emails), ""
        return [], ""
