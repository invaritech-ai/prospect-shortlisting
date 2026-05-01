# Scraper Reliability Design

Date: 2026-05-01

## Goal

Improve company-level scrape success while keeping easy sites fast and handling impossible sites cleanly.

Success is not all-or-nothing:

- `full_success`: important discovered targets were fetched, with no material failures.
- `partial_success`: fetched `home` plus one useful page, or fetched two useful pages of any kind.
- `failed_gracefully`: no useful pages were fetched, with a clear terminal reason.

## Current Shape

The scraper currently runs:

```text
static httpx -> curl_cffi impersonate -> Scrapling stealth
```

The largest observed problems are:

- Remote Browserless CDP returns `429 Too Many Requests`.
- Apex HTTPS often fails TLS while `www` or HTTP redirect works.
- Discovery sometimes selects plausible but wrong page URLs.
- Some domains are genuinely blocked by WAF, geo restrictions, CAPTCHA, or redirect loops.

## Recommended Approach

Use the existing architecture, but remove Browserless and add smarter recovery before browser escalation.

The new pipeline remains:

```text
static httpx -> curl_cffi impersonate -> local Scrapling browser -> classified outcome
```

## Runtime Changes

### 1. Remove Browserless Runtime Path

`PS_BROWSERLESS_URL` should no longer control stealth fetch behavior.

Stealth fetches always use local Scrapling browser sessions. Documentation and `.env.example` should stop presenting Browserless as the supported worker path.

### 2. Configure Local Scrapling

Add explicit local-browser settings:

- `scrape_stealth_max_pages`
- `scrape_stealth_block_images`
- `scrape_stealth_disable_resources`
- `scrape_stealth_humanize`
- `scrape_stealth_os_randomize`
- optional future `scrape_proxy_url`

Proxy support is a later add-on. The setting can exist, but the first pass should not depend on having a proxy provider.

### 3. Canonical Host Recovery

When a page fails on `https://domain/...`, but the job has already found a working same-domain origin such as `https://www.domain/...`, retry the failed page on the working origin before escalating to browser.

Example:

```text
https://actusa.net/about       -> TLS error
https://www.actusa.net/        -> works
retry as:
https://www.actusa.net/about
```

Recovery must be conservative:

- Allow `apex <-> www` rewrites.
- Allow redirects that stay clearly within the same company domain.
- Do not blindly rewrite onto unrelated acquisition domains unless separately allowed.

### 4. Preserve Partial Success

Subpage failures should be recorded, not treated as company failure, when enough useful content was fetched.

The job remains usable if it fetched:

- `home` plus one useful page, or
- two useful pages of any kind.

### 5. Clear Terminal Reasons

If no useful pages are fetched, the job should finish with a specific reason:

- `dns_not_resolved`
- `tls_error`
- `bot_protection`
- `geo_restricted`
- `redirect_loop`
- `browser_unavailable`
- `no_pages_fetched`
- `parked_domain`
- `access_denied`

These reasons should be visible in logs and persisted on the scrape job/page records.

## Speed Policy

Keep static and impersonate tiers first. They are cheaper and faster than browser automation.

Use local Scrapling only for pages that still need it. Batch those pages into one Scrapling session per company instead of launching one browser per URL.

Initial operating recommendation:

- worker scrape concurrency: `2` or `3`
- Scrapling `max_pages`: `2`

This avoids accidentally running too many local browser pages at once.

## Validation

Use a fixed benchmark set from observed logs:

- `a1bearing.com`
- `acopian.com`
- `acterminals.com`
- `actionfabricating.com`
- `actuant.com`
- `actusa.net`
- `addisonelectric.com`
- `advantech.com`
- `advice1.com`

Measure:

- company usable rate
- pages fetched per company
- average job duration
- browser fallback rate
- top terminal error codes

## Implementation Notes

Likely files:

- `app/core/config.py`
- `app/services/fetch_service.py`
- `app/services/scrape_service.py`
- `app/services/url_utils.py`
- `.env.example`
- `README.md`
- focused tests around canonical host recovery and outcome classification

The first implementation pass should avoid broad scraper rewrites. The main behavioral changes are local-only stealth fetches, conservative origin recovery, and clearer success/failure classification.
