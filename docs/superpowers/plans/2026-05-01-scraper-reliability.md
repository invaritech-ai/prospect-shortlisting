# Scraper Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove remote Browserless dependency, improve same-company canonical host recovery, and classify scraper outcomes as full success, partial success, or graceful failure.

**Architecture:** Keep the existing tiered scraper: static `httpx`, then `curl_cffi` impersonation, then local Scrapling browser. Add small helper functions around stealth settings, safe origin rewriting, and scrape outcome classification rather than rewriting the whole pipeline.

**Tech Stack:** FastAPI backend, SQLModel/SQLAlchemy, Procrastinate workers, Scrapling, pytest, ruff.

---

## File Map

- Modify: `app/core/config.py`
  - Add local Scrapling settings.
  - Keep or deprecate `browserless_url`, but stop using it in fetch code.

- Modify: `app/services/fetch_service.py`
  - Remove Browserless/CDP branching from stealth fetch/session kwargs.
  - Add `BROWSER_UNAVAILABLE`, `REDIRECT_LOOP`, and `GEO_RESTRICTED` error taxonomy where detectable.
  - Make stealth session kwargs local-browser only.

- Modify: `app/services/url_utils.py`
  - Add safe same-domain origin rewrite helpers.

- Modify: `app/services/scrape_service.py`
  - Track the first working origin for the job.
  - Retry failed page targets on that working origin before browser escalation.
  - Classify final job outcome without losing existing `state="succeeded"` compatibility for usable partial scrapes.

- Modify: `.env.example`
  - Remove Browserless instructions.
  - Add local stealth settings.

- Modify: `README.md`
  - Update worker guidance and scrape behavior notes.

- Test: `tests/test_fetch_tls_recovery.py`
  - Extend existing host recovery tests.

- Test: `tests/test_fetch_service_taxonomy.py`
  - Add local stealth config/error taxonomy tests.

- Test: `tests/test_scrape_outcome_classification.py`
  - New unit tests for full/partial/failure classification.

---

## Task 1: Local-Only Scrapling Stealth Settings

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/services/fetch_service.py`
- Modify: `tests/test_fetch_service_taxonomy.py`

- [ ] **Step 1: Write failing tests for local-only stealth kwargs**

Add to `tests/test_fetch_service_taxonomy.py`:

```python
def test_stealth_session_kwargs_are_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_service.settings, "browserless_url", "wss://example.invalid/stealth")
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_max_pages", 2, raising=False)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_block_images", True, raising=False)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_disable_resources", True, raising=False)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_humanize", True, raising=False)
    monkeypatch.setattr(fetch_service.settings, "scrape_stealth_os_randomize", True, raising=False)
    monkeypatch.setattr(fetch_service.settings, "scrape_proxy_url", "", raising=False)

    kwargs = fetch_service._stealth_session_kwargs()

    assert "cdp_url" not in kwargs
    assert kwargs["max_pages"] == 2
    assert kwargs["block_images"] is True
    assert kwargs["disable_resources"] is True
    assert kwargs["humanize"] is True
    assert kwargs["os_randomize"] is True
    assert "proxy" not in kwargs
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_fetch_service_taxonomy.py::test_stealth_session_kwargs_are_local_only -q
```

Expected: FAIL because the new settings do not exist or `cdp_url` is still present.

- [ ] **Step 3: Add config settings**

In `app/core/config.py`, add after `scrape_stealth_demotion_streak`:

```python
    scrape_stealth_max_pages: int = 2
    scrape_stealth_block_images: bool = True
    scrape_stealth_disable_resources: bool = True
    scrape_stealth_humanize: bool = True
    scrape_stealth_os_randomize: bool = True
    scrape_proxy_url: str = ""
```

- [ ] **Step 4: Make stealth kwargs local-only**

In `app/services/fetch_service.py`, update `_stealth_fetch()` and `_stealth_session_kwargs()` so neither function adds `cdp_url`.

Use this shape for `_stealth_session_kwargs()`:

```python
def _stealth_session_kwargs() -> dict:
    """Build local Scrapling AsyncStealthySession kwargs from settings."""
    kwargs: dict = {
        "headless": True,
        "timeout": settings.scrape_stealth_timeout_ms,
        "network_idle": True,
        "solve_cloudflare": True,
        "block_webrtc": True,
        "hide_canvas": True,
        "max_pages": settings.scrape_stealth_max_pages,
        "block_images": settings.scrape_stealth_block_images,
        "disable_resources": settings.scrape_stealth_disable_resources,
        "humanize": settings.scrape_stealth_humanize,
        "os_randomize": settings.scrape_stealth_os_randomize,
        "selector_config": {**StealthyFetcher._generate_parser_arguments()},
    }
    proxy_url = settings.scrape_proxy_url.strip()
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return kwargs
```

Update log mode strings from `"browserless" if settings.browserless_url else "local"` to `"local"` in both stealth paths.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_fetch_service_taxonomy.py::test_stealth_session_kwargs_are_local_only tests/test_fetch_tls_recovery.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/services/fetch_service.py tests/test_fetch_service_taxonomy.py
git commit -m "fix: use local scrapling stealth fetches"
```

---

## Task 2: Safe Canonical Origin Recovery

**Files:**
- Modify: `app/services/url_utils.py`
- Modify: `tests/test_fetch_tls_recovery.py`

- [ ] **Step 1: Write failing tests for safe origin rewrite**

Add to `tests/test_fetch_tls_recovery.py`:

```python
from app.services.url_utils import rewrite_to_working_origin


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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_fetch_tls_recovery.py::test_rewrite_to_working_origin_allows_apex_to_www tests/test_fetch_tls_recovery.py::test_rewrite_to_working_origin_rejects_unrelated_domain -q
```

Expected: FAIL because `rewrite_to_working_origin` does not exist.

- [ ] **Step 3: Implement helper**

Add to `app/services/url_utils.py`:

```python
def same_company_host(host: str, domain: str) -> bool:
    normalized_host = (host or "").lower().split("@")[-1].split(":")[0]
    normalized_domain = (domain or "").lower()
    if normalized_host.startswith("www."):
        normalized_host = normalized_host[4:]
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]
    return normalized_host == normalized_domain


def rewrite_to_working_origin(url: str, working_origin_url: str, domain: str) -> str:
    """Rewrite `url` onto a known-good apex/www origin for the same company domain."""
    parsed_url = urlparse(url)
    parsed_origin = urlparse(working_origin_url)
    if not parsed_url.netloc or not parsed_origin.netloc:
        return ""
    if not same_company_host(parsed_url.netloc, domain):
        return ""
    if not same_company_host(parsed_origin.netloc, domain):
        return ""

    rewritten = parsed_url._replace(
        scheme=(parsed_origin.scheme or parsed_url.scheme or "https").lower(),
        netloc=parsed_origin.netloc.lower(),
    )
    return canonical_internal_url(urlunparse(rewritten), domain)
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_fetch_tls_recovery.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/url_utils.py tests/test_fetch_tls_recovery.py
git commit -m "fix: add safe scrape origin rewriting"
```

---

## Task 3: Use Working Origin Before Browser Escalation

**Files:**
- Modify: `app/services/scrape_service.py`
- Modify: `tests/test_fetch_tls_recovery.py`

- [ ] **Step 1: Write failing test for origin retry decision**

Add a pure helper test to `tests/test_fetch_tls_recovery.py`:

```python
from app.services.scrape_service import retry_url_for_working_origin


def test_retry_url_for_working_origin_only_for_recoverable_errors() -> None:
    retry = retry_url_for_working_origin(
        canonical="https://actusa.net/about",
        working_origin_url="https://www.actusa.net/",
        domain="actusa.net",
        error_code="tls_error",
    )
    assert retry == "https://www.actusa.net/about"

    no_retry = retry_url_for_working_origin(
        canonical="https://actusa.net/missing",
        working_origin_url="https://www.actusa.net/",
        domain="actusa.net",
        error_code="not_found",
    )
    assert no_retry == ""
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_fetch_tls_recovery.py::test_retry_url_for_working_origin_only_for_recoverable_errors -q
```

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Add helper to scrape service**

In `app/services/scrape_service.py`, import `rewrite_to_working_origin` and add:

```python
_ORIGIN_RETRY_ERROR_CODES = frozenset({
    FetchErrorCode.TLS_ERROR,
    FetchErrorCode.ACCESS_DENIED,
    FetchErrorCode.FETCH_FAILED,
    FetchErrorCode.TIMEOUT,
})


def retry_url_for_working_origin(
    *,
    canonical: str,
    working_origin_url: str,
    domain: str,
    error_code: str,
) -> str:
    if not working_origin_url or error_code not in _ORIGIN_RETRY_ERROR_CODES:
        return ""
    rewritten = rewrite_to_working_origin(canonical, working_origin_url, domain)
    if not rewritten or rewritten == canonical:
        return ""
    return rewritten
```

- [ ] **Step 4: Wire helper into Phase 5 fetch loop**

In `ScrapeService.run_scrape`, initialize before the `for kind, canonical, depth in page_plan:` loop:

```python
        working_origin_url = ""
```

Inside the loop, after a successful `tier_result.selector is not None`, set:

```python
                if not working_origin_url:
                    working_origin_url = tier_result.final_url
```

After a failed `tier_result`, before adding to `stealth_needed`, add:

```python
            retry_url = retry_url_for_working_origin(
                canonical=canonical,
                working_origin_url=working_origin_url,
                domain=domain,
                error_code=tier_result.error_code,
            )
            if retry_url:
                retry_result = await scrape_page_fetch(
                    retry_url, domain, job_id=str(job_id), policy=policy,
                )
                if retry_result.selector is not None:
                    static_results[canonical] = retry_result
                    if not working_origin_url:
                        working_origin_url = retry_result.final_url
                    logger.info(
                        "scrape_origin_retry_success kind=%s url=%s retry_url=%s mode=%s",
                        kind, canonical, retry_url, retry_result.fetch_mode,
                    )
                    continue
                tier_result = retry_result
```

Keep result keys as the original `canonical` so page processing still follows the existing `page_plan`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_fetch_tls_recovery.py tests/test_fetch_service_taxonomy.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/scrape_service.py tests/test_fetch_tls_recovery.py
git commit -m "fix: retry scrape pages on working origin"
```

---

## Task 4: Outcome Classification

**Files:**
- Modify: `app/services/scrape_service.py`
- Create: `tests/test_scrape_outcome_classification.py`

- [ ] **Step 1: Write outcome tests**

Create `tests/test_scrape_outcome_classification.py`:

```python
from app.services.scrape_service import classify_scrape_outcome


def test_classify_scrape_outcome_full_success() -> None:
    outcome = classify_scrape_outcome([
        {"success": True, "page_kind": "home", "text_len": 1000},
        {"success": True, "page_kind": "about", "text_len": 900},
        {"success": True, "page_kind": "products", "text_len": 800},
    ])
    assert outcome == ("full_success", "")


def test_classify_scrape_outcome_partial_home_plus_one() -> None:
    outcome = classify_scrape_outcome([
        {"success": True, "page_kind": "home", "text_len": 1000},
        {"success": True, "page_kind": "contact", "text_len": 500},
        {"success": False, "page_kind": "products", "fetch_error_code": "not_found"},
    ])
    assert outcome == ("partial_success", "")


def test_classify_scrape_outcome_partial_two_non_home_pages() -> None:
    outcome = classify_scrape_outcome([
        {"success": True, "page_kind": "about", "text_len": 800},
        {"success": True, "page_kind": "services", "text_len": 700},
    ])
    assert outcome == ("partial_success", "")


def test_classify_scrape_outcome_no_pages_uses_dominant_failure() -> None:
    outcome = classify_scrape_outcome([
        {"success": False, "page_kind": "home", "fetch_error_code": "tls_error"},
        {"success": False, "page_kind": "about", "fetch_error_code": "tls_error"},
        {"success": False, "page_kind": "products", "fetch_error_code": "not_found"},
    ])
    assert outcome == ("failed_gracefully", "tls_error")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_scrape_outcome_classification.py -q
```

Expected: FAIL because `classify_scrape_outcome` does not exist.

- [ ] **Step 3: Implement classifier**

Add to `app/services/scrape_service.py`:

```python
def classify_scrape_outcome(fetched_pages: list[dict]) -> tuple[str, str]:
    successful = [
        p for p in fetched_pages
        if p.get("success") and int(p.get("text_len") or 0) >= 80
    ]
    failures = [p for p in fetched_pages if not p.get("success")]
    has_home = any(p.get("page_kind") == "home" for p in successful)

    if successful and not failures:
        return ("full_success", "")
    if has_home and len(successful) >= 2:
        return ("partial_success", "")
    if len(successful) >= 2:
        return ("partial_success", "")

    failure_codes = [
        str(p.get("fetch_error_code") or "")
        for p in failures
        if str(p.get("fetch_error_code") or "")
    ]
    if failure_codes:
        dominant = max(set(failure_codes), key=failure_codes.count)
        return ("failed_gracefully", dominant)
    return ("failed_gracefully", "no_pages_fetched")
```

- [ ] **Step 4: Use classifier when writing job result**

In the final DB write block in `run_scrape`, before setting `job.state`, compute:

```python
            scrape_outcome, terminal_code = classify_scrape_outcome(fetched_pages)
```

Keep compatibility:

```python
            if markdown_pages == 0:
                job.state = "failed"
                job.failure_reason = "unknown"
                job.last_error_code = terminal_code or "no_markdown_produced"
                job.last_error_message = "Scrape completed but produced no markdown pages."
            else:
                job.state = "succeeded"
                job.failure_reason = None
                job.last_error_code = None if scrape_outcome in {"full_success", "partial_success"} else terminal_code
                job.last_error_message = None
```

Do not add a new DB column in this pass. Use logs for `scrape_outcome`:

```python
                scrape_outcome=scrape_outcome,
```

inside the final `scrape_completed` log event.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_scrape_outcome_classification.py tests/test_fetch_tls_recovery.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/scrape_service.py tests/test_scrape_outcome_classification.py
git commit -m "fix: classify scrape outcomes"
```

---

## Task 5: Docs and Env Cleanup

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update `.env.example`**

Remove the Browserless section and add:

```dotenv
# Local Scrapling browser fallback.
# Used only after static and impersonating fetches fail.
PS_SCRAPE_STEALTH_MAX_PAGES=2
PS_SCRAPE_STEALTH_BLOCK_IMAGES=true
PS_SCRAPE_STEALTH_DISABLE_RESOURCES=true
PS_SCRAPE_STEALTH_HUMANIZE=true
PS_SCRAPE_STEALTH_OS_RANDOMIZE=true

# Optional future proxy provider. Leave blank unless configured.
PS_SCRAPE_PROXY_URL=
```

- [ ] **Step 2: Update README worker guidance**

Replace any Browserless worker guidance with:

```bash
PS_WORKER_PROCESS=1 uv run python -m procrastinate --app=app.queue.app worker -q scrape -c 2
```

Add a note:

```markdown
The scrape worker uses static fetches first, then curl_cffi impersonation, then local Scrapling browser fallback. Browser fallback is intentionally local-only; `PS_BROWSERLESS_URL` is not used by the scraper.
```

- [ ] **Step 3: Run text search**

Run:

```bash
rg -n "Browserless|BROWSERLESS|browserless|PS_BROWSERLESS_URL|cdp_url" README.md .env.example app/services/fetch_service.py app/core/config.py
```

Expected: no runtime Browserless references in `README.md`, `.env.example`, or `fetch_service.py`. `app/core/config.py` may keep `browserless_url` only if intentionally deprecated.

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example
git commit -m "docs: document local scrape fallback"
```

---

## Task 6: Verification Pass

**Files:**
- No required source changes.

- [ ] **Step 1: Run focused unit tests**

```bash
uv run pytest tests/test_fetch_service_taxonomy.py tests/test_fetch_tls_recovery.py tests/test_scrape_outcome_classification.py tests/test_domain_policy.py -q
```

Expected: PASS.

- [ ] **Step 2: Run ruff on changed files**

```bash
uv run ruff check app/core/config.py app/services/fetch_service.py app/services/scrape_service.py app/services/url_utils.py tests/test_fetch_service_taxonomy.py tests/test_fetch_tls_recovery.py tests/test_scrape_outcome_classification.py
```

Expected: PASS.

- [ ] **Step 3: Optional local benchmark**

Run a small scrape batch manually against:

```text
a1bearing.com
acopian.com
acterminals.com
actionfabricating.com
actuant.com
actusa.net
addisonelectric.com
advantech.com
advice1.com
```

Record:

```text
company usable rate
pages fetched per company
average job duration
browser fallback rate
top terminal error codes
```

Use this only as operational validation; do not make the unit tests depend on live domains.

---

## Self-Review

- Spec coverage:
  - Browserless removal: Task 1 and Task 5.
  - Local Scrapling settings: Task 1.
  - Canonical host recovery: Task 2 and Task 3.
  - Partial success semantics: Task 4.
  - Graceful terminal reasons: Task 4.
  - Validation/benchmark: Task 6.

- Placeholder scan:
  - No `TBD`, `TODO`, or unspecified test instructions.

- Type consistency:
  - Helper names are stable: `rewrite_to_working_origin`, `retry_url_for_working_origin`, `classify_scrape_outcome`.
  - Existing `ScrapeJob.state` compatibility is preserved: usable partial scrapes still write `state="succeeded"`.
