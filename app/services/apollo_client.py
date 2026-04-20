"""Apollo API client: people search and enrichment helpers."""
from __future__ import annotations

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

logger = logging.getLogger(__name__)

_APOLLO_BASE = "https://api.apollo.io/api/v1"
_SSL_CTX = ssl.create_default_context()

ERR_APOLLO_CREDENTIALS_MISSING = "apollo_credentials_missing"
ERR_APOLLO_AUTH_FAILED = "apollo_auth_failed"
ERR_APOLLO_RATE_LIMITED = "apollo_rate_limited"
ERR_APOLLO_TIMEOUT = "apollo_timeout"
ERR_APOLLO_FAILED = "apollo_failed"


class ApolloClient:
    """Apollo API client.

    The client uses the documented Apollo API key header and exponential
    backoff on 429 / 5xx responses.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        min_interval_sec: float = 0.6,
        default_timeout: int = 30,
    ) -> None:
        self._api_key = ""
        self._max_retries = max_retries
        self._min_interval = min_interval_sec
        self._default_timeout = default_timeout
        self._last_call_at: float = 0.0
        self.last_error_code: str = ""

    def _resolved_api_key(self) -> str:
        return credentials_resolver.resolve("apollo", "api_key") or (self._api_key or "").strip()

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call_at
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)

    def _do_request(self, req: Request, timeout: int) -> tuple[dict, str]:
        last_exc: Exception | None = None
        self.last_error_code = ""
        for attempt in range(self._max_retries + 1):
            try:
                with urlopen(req, context=_SSL_CTX, timeout=timeout) as resp:  # noqa: S310
                    raw = resp.read().decode("utf-8", errors="ignore")
                self._last_call_at = time.monotonic()
                data = json.loads(raw) if raw else {}
                return data, ""
            except HTTPError as exc:
                last_exc = exc
                if exc.code in (401, 403):
                    log_event(logger, "apollo_auth_failed", status=exc.code, url=req.full_url)
                    self.last_error_code = ERR_APOLLO_AUTH_FAILED
                    return {}, ERR_APOLLO_AUTH_FAILED
                if exc.code == 429 and attempt < self._max_retries:
                    delay = 2.0 * (2 ** attempt)
                    log_event(logger, "apollo_429_retry", attempt=attempt + 1, delay_sec=delay)
                    time.sleep(delay)
                    continue
                if exc.code >= 500 and attempt < self._max_retries:
                    delay = 2.0 * (2 ** attempt)
                    log_event(logger, "apollo_5xx_retry", status=exc.code, attempt=attempt + 1, delay_sec=delay)
                    time.sleep(delay)
                    continue
                if exc.code == 429:
                    self.last_error_code = ERR_APOLLO_RATE_LIMITED
                    return {}, ERR_APOLLO_RATE_LIMITED
                if exc.code >= 500:
                    self.last_error_code = ERR_APOLLO_FAILED
                    return {}, ERR_APOLLO_FAILED
                log_event(logger, "apollo_http_error", status=exc.code, url=req.full_url)
                self.last_error_code = ERR_APOLLO_FAILED
                return {}, ERR_APOLLO_FAILED
            except TimeoutError:
                log_event(logger, "apollo_timeout", url=req.full_url)
                self.last_error_code = ERR_APOLLO_TIMEOUT
                return {}, ERR_APOLLO_TIMEOUT
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log_event(logger, "apollo_error", error=str(exc), traceback=traceback.format_exc())
                self.last_error_code = ERR_APOLLO_FAILED
                return {}, ERR_APOLLO_FAILED
        log_event(logger, "apollo_retries_exhausted", error=str(last_exc))
        self.last_error_code = ERR_APOLLO_FAILED
        return {}, ERR_APOLLO_FAILED

    def _post_json(
        self,
        path: str,
        *,
        query_params: dict[str, object] | None = None,
        payload: dict[str, object] | None = None,
        timeout: int | None = None,
    ) -> tuple[dict, str]:
        self._throttle()
        api_key = self._resolved_api_key()
        url = f"{_APOLLO_BASE}{path}"
        if query_params:
            query = urlencode(query_params, doseq=True)
            url = f"{url}?{query}"
        body = json.dumps(payload or {}).encode("utf-8")
        req = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "Accept": "application/json",
                "X-Api-Key": api_key,
            },
        )
        return self._do_request(req, timeout or self._default_timeout)

    @staticmethod
    def _extract_people(data: dict) -> list[dict]:
        people = data.get("people")
        if isinstance(people, list):
            return [p for p in people if isinstance(p, dict)]
        matches = data.get("matches")
        if isinstance(matches, list):
            return [p for p in matches if isinstance(p, dict)]
        results = data.get("results")
        if isinstance(results, list):
            return [p for p in results if isinstance(p, dict)]
        return []

    def search_people(
        self,
        domain: str,
        page: int = 1,
        person_titles: list[str] | None = None,
    ) -> list[dict]:
        """Search Apollo's people database for a company domain.

        If person_titles is provided, Apollo pre-filters by job title,
        reducing results to relevant contacts and saving API credits.
        """
        if not self._resolved_api_key():
            self.last_error_code = ERR_APOLLO_CREDENTIALS_MISSING
            return []

        params: dict[str, object] = {
            "q_organization_domains_list[]": [domain],
            "page": page,
            "per_page": 100,
        }
        if person_titles:
            params["person_titles[]"] = person_titles

        data, err = self._post_json("/mixed_people/api_search", query_params=params)
        if err:
            return []
        self.last_error_code = ""
        return self._extract_people(data)

    def reveal_email(self, person_id: str) -> dict | None:
        """Enrich a single person record to reveal an email address."""
        if not self._resolved_api_key():
            self.last_error_code = ERR_APOLLO_CREDENTIALS_MISSING
            return None

        data, err = self._post_json(
            "/people/bulk_match",
            query_params={
                "reveal_personal_emails": "true",
                "reveal_phone_number": "false",
            },
            payload={"details": [{"id": person_id}]},
        )
        if err:
            return None
        self.last_error_code = ""

        matches = self._extract_people(data)
        if matches:
            return matches[0]

        person = data.get("person")
        if isinstance(person, dict):
            return person
        return None
