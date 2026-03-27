# Browserless API Reference

> Remote browser automation service. Offers both WebSocket (CDP) and REST APIs.
> Auth: API token as query param `?token=YOUR_TOKEN`.
> Plan: 1,000 credits/month, 2 concurrent sessions.

---

## Regional Endpoints

| Region | Host |
|--------|------|
| US West (SFO) | `production-sfo.browserless.io` |
| Europe (London) | `production-lon.browserless.io` |
| Europe (Amsterdam) | `production-ams.browserless.io` |

Use `https://` for REST APIs, `wss://` for CDP WebSocket.

---

## CDP WebSocket (Browser-as-a-Service)

Connect via Puppeteer `connect()` or Playwright `connectOverCDP()`.

### Connection URLs

| Browser | URL |
|---------|-----|
| Chromium (default) | `wss://production-sfo.browserless.io/chromium?token=TOKEN` |
| Chrome (branded) | `wss://production-sfo.browserless.io/chrome?token=TOKEN` |
| Stealth (fingerprint randomization) | `wss://production-sfo.browserless.io/stealth?token=TOKEN` |
| Firefox (Playwright) | `wss://production-sfo.browserless.io/firefox/playwright?token=TOKEN` |
| WebKit (Playwright) | `wss://production-sfo.browserless.io/webkit/playwright?token=TOKEN` |

### Puppeteer Example
```javascript
import puppeteer from "puppeteer-core";
const browser = await puppeteer.connect({
  browserWSEndpoint: "wss://production-sfo.browserless.io?token=YOUR_TOKEN",
});
const page = await browser.newPage();
await page.goto("https://example.com");
console.log(await page.title());
await browser.close();
```

### Playwright Example
```python
from playwright.async_api import async_playwright
async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp(
        "wss://production-sfo.browserless.io?token=YOUR_TOKEN"
    )
```

### Session Limits by Plan
| Plan | Max Session Duration |
|------|---------------------|
| Free | 1 minute |
| Scale+ | 60+ minutes |

---

## REST APIs

All REST endpoints: `POST https://production-sfo.browserless.io/{endpoint}?token=TOKEN`

### Shared Request Options

These options apply across all REST endpoints:

| Option | Type | Description |
|--------|------|-------------|
| `url` | string | Target URL (mutually exclusive with `html`) |
| `html` | string | Inline HTML to render |
| `gotoOptions` | object | Navigation options (waitUntil, timeout, etc.) |
| `waitForSelector` | object | Wait for CSS selector before proceeding |
| `waitForEvent` | object | Wait for page event |
| `waitForFunction` | object | Wait for JS function to return truthy |
| `waitForTimeout` | number | Wait N milliseconds |
| `rejectResourceTypes` | array | Block resource types (image, stylesheet, font, etc.) |
| `rejectRequestPattern` | array | Block URLs matching patterns |
| `bestAttempt` | bool | Continue on async failures |
| `addScriptTag` | array | Inject scripts before processing |
| `addStyleTag` | array | Inject styles before processing |

---

### `/content` — Get Rendered HTML
```
POST /content?token=TOKEN
Content-Type: application/json
```
Returns fully rendered HTML (JavaScript-executed DOM) as `text/html`.

| Param | Required | Description |
|-------|----------|-------------|
| `url` | Yes* | URL to render |
| `html` | Yes* | Inline HTML (*one of url/html required) |

**Response:** `text/html` — full page HTML after JS execution.

**cURL example:**
```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}' \
  'https://production-sfo.browserless.io/content?token=TOKEN'
```

---

### `/scrape` — Extract Structured Data
```
POST /scrape?token=TOKEN
Content-Type: application/json
```
| Param | Required | Description |
|-------|----------|-------------|
| `url` | Yes | URL to scrape |
| `elements` | Yes | Array of `{selector: "css selector"}` objects |

**Response:**
```json
{
  "data": [
    {
      "selector": "h1",
      "results": [
        {
          "text": "extracted text",
          "html": "<h1>...</h1>",
          "attributes": [{"name": "class", "value": "..."}],
          "height": 120, "width": 736, "top": 196, "left": 32
        }
      ]
    }
  ]
}
```

---

### `/unblock` — Bypass Bot Detection & CAPTCHAs
```
POST /unblock?token=TOKEN
Content-Type: application/json
```
| Param | Required | Description |
|-------|----------|-------------|
| `url` | Yes | URL to unblock |
| `content` | No | `true` to return HTML |
| `cookies` | No | `true` to return cookies |
| `screenshot` | No | `true` to return base64 PNG |
| `browserWSEndpoint` | No | `true` to get a CDP WebSocket URL for further automation |
| `ttl` | No | Session lifetime in ms (when using browserWSEndpoint) |

**Response:**
```json
{
  "content": "HTML string or null",
  "cookies": [{"name": "...", "value": "...", "domain": "...", ...}],
  "screenshot": "base64 string or null",
  "browserWSEndpoint": "wss://... or null"
}
```

**Note:** For advanced CAPTCHA solving (reCAPTCHA, Cloudflare Turnstile), use BrowserQL with `solve` mutation.
Best results when combined with residential proxy: `?proxy=residential`.

---

### `/screenshot` — Capture Page Image
```
POST /screenshot?token=TOKEN
Content-Type: application/json
```
| Param | Required | Description |
|-------|----------|-------------|
| `url` | Yes* | URL to capture |
| `html` | Yes* | Inline HTML (*one of url/html) |
| `options.type` | No | `png` (default), `jpeg`, `webp` |
| `options.fullPage` | No | `true` for full page height |

**Response:** Binary image (`image/png`, `image/jpeg`, or `image/webp`).

---

### `/pdf` — Generate PDF
```
POST /pdf?token=TOKEN
Content-Type: application/json
```
| Param | Required | Description |
|-------|----------|-------------|
| `url` | Yes* | URL to render |
| `html` | Yes* | Inline HTML |

**Response:** Binary PDF (`application/pdf`).

---

### `/function` — Run Custom Puppeteer Code
```
POST /function?token=TOKEN
Content-Type: application/json
```
Executes custom Puppeteer scripts server-side.

---

### `/download` — Retrieve Files
```
POST /download?token=TOKEN
```
Fetches files that Chrome downloads during page execution.

---

### `/export` — Stream Native Content
```
POST /export?token=TOKEN
```
Fetches a URL and streams it in its native content type.

---

### `/performance` — Lighthouse Audit
```
POST /performance?token=TOKEN
```
Runs Lighthouse audits for SEO, accessibility, and performance metrics.

---

## All REST Endpoints Summary

| Endpoint | Purpose | Response Type |
|----------|---------|--------------|
| `/content` | Full rendered HTML | `text/html` |
| `/scrape` | Structured data via CSS selectors | `application/json` |
| `/unblock` | Bot detection / CAPTCHA bypass | `application/json` |
| `/screenshot` | Page screenshot | `image/png` |
| `/pdf` | PDF generation | `application/pdf` |
| `/function` | Custom Puppeteer code | varies |
| `/download` | File download | varies |
| `/export` | Native content stream | varies |
| `/performance` | Lighthouse audit | `application/json` |

---

## Current Integration

**Configured URL in `.env`:**
```
PS_BROWSERLESS_URL=https://production-sfo.browserless.io/chrome/content?token=TOKEN
```
This is the `/content` REST endpoint (returns rendered HTML).

**CDP WebSocket equivalent (for Scrapling/Playwright):**
```
wss://production-sfo.browserless.io/stealth?token=TOKEN
```
Use `/stealth` path for fingerprint randomization (best for anti-bot).

---

## Credit & Concurrency Limits

| Limit | Value |
|-------|-------|
| Credits/month | 1,000 |
| Concurrent sessions | 2 |
| Session timeout (free) | 1 minute |

When credits are exhausted, Browserless workers should gracefully degrade — the deterministic worker split ensures local Chromium workers continue unaffected.
