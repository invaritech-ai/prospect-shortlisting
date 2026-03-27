# Snov.io API Reference

> Complete API reference for Snov.io integration. Base URL: `https://api.snov.io`
> Rate limit: **60 requests/minute**. All endpoints require Bearer token auth unless noted.

---

## Authentication

### Get Access Token
```
POST /v1/oauth/access_token
Content-Type: application/x-www-form-urlencoded
```
| Param | Required | Description |
|-------|----------|-------------|
| `grant_type` | Yes | `"client_credentials"` |
| `client_id` | Yes | From Snov account settings |
| `client_secret` | Yes | From Snov account settings |

**Response:**
```json
{"access_token": "...", "token_type": "Bearer", "expires_in": 3600}
```

All subsequent calls use `Authorization: Bearer {access_token}` header.

---

## Email Finder & Data Enrichment

### 1. Domain Search (Company Info)
```
POST /v2/domain-search/start          → returns task_hash
GET  /v2/domain-search/result/{hash}  → company info
```
**Cost:** 1 credit per unique request + 1 credit per prospect with email
| Param | Required | Description |
|-------|----------|-------------|
| `domain` | Yes | Company domain |

**Response:** Company name, city, founded year, website, phone, industry, size, related domains.

### 2. Prospect Profiles by Domain
```
POST /v2/domain-search/prospects/start          → returns task_hash
GET  /v2/domain-search/prospects/result/{hash}  → prospect list
```
| Param | Required | Description |
|-------|----------|-------------|
| `domain` | Yes | Company domain |
| `positions[]` | No | Filter by job titles (max 10) |
| `page` | No | Page number, 20 results/page |

**Response fields:** `first_name`, `last_name`, `position`, `source_page`, `search_emails_start` (hash for email lookup).

### 3. Prospect Email Lookup
```
POST /v2/domain-search/prospects/search-emails/start/{prospect_hash}   → task_hash
GET  /v2/domain-search/prospects/search-emails/result/{task_hash}      → emails
```
**Cost:** 1 credit per prospect with email found.
**Response:** `emails[]` with `email` and `smtp_status` (`valid`/`unknown`).

### 4. Domain Emails (All Emails for Domain)
```
POST /v2/domain-search/domain-emails/start          → task_hash
GET  /v2/domain-search/domain-emails/result/{hash}   → emails
```
**Cost:** 1 credit per unique request.
| Param | Required | Description |
|-------|----------|-------------|
| `domain` | Yes | Company domain |

**Response:** Unverified `email` addresses, `total_count`, pagination via `next`.

### 5. Generic Contacts (role-based emails)
```
POST /v2/domain-search/generic-contacts/start          → task_hash
GET  /v2/domain-search/generic-contacts/result/{hash}   → generic emails
```
**Cost:** 1 credit per unique request.
**Response:** Generic addresses like `sales@`, `orders@`, `info@`.

### 6. Email Count Check (FREE)
```
POST /v1/get-domain-emails-count
```
| Param | Required | Description |
|-------|----------|-------------|
| `domain` | Yes | Company domain |

**Response:** `{"domain": "...", "webmail": false, "result": 42}`

### 7. Email Finder by Name + Domain
```
POST /v2/emails-by-domain-by-name/start          → task_hash
GET  /v2/emails-by-domain-by-name/result?task_hash={hash}
```
**Cost:** 1 credit per email found with valid/unknown status.
| Param | Required | Description |
|-------|----------|-------------|
| `rows` | Yes | Array of `{first_name, last_name, domain}` (max 10) |
| `webhook_url` | No | Webhook for instant results |

**Response fields:** `email`, `smtp_status`, `is_valid_format`, `is_disposable`, `is_webmail`, `is_gibberish`, `unknown_status_reason`.

### 8. Company Domain by Name
```
POST /v2/company-domain-by-name/start          → task_hash
GET  /v2/company-domain-by-name/result?task_hash={hash}
```
**Cost:** 1 credit per domain found.
| Param | Required | Description |
|-------|----------|-------------|
| `names[]` | Yes | Company names (max 10) |
| `webhook_url` | No | Optional |

**Response:** `name`, `domain` for each company.

### 9. LinkedIn Profile Info from URLs
```
POST /v2/li-profiles-by-urls/start          → task_hash
GET  /v2/li-profiles-by-urls/result?task_hash={hash}
```
**Cost:** 1 credit per profile.
| Param | Required | Description |
|-------|----------|-------------|
| `urls[]` | Yes | LinkedIn profile URLs (max 10) |
| `webhook_url` | No | Optional |

**Response:** `name`, `first_name`, `last_name`, `industry`, `location`, `country`, `skills`, `positions[]` (with company details).

### 10. Enrich Person Profile from Email
```
POST /v1/get-profile-by-email
```
**Cost:** 1 credit (free if no results).
| Param | Required | Description |
|-------|----------|-------------|
| `email` | Yes | Email address |

**Response:** `id`, `source`, `name`, `firstName`, `lastName`, `logo`, `industry`, `country`, `locality`, `social` links, `currentJobs[]`, `previousJobs[]`, `lastUpdateDate`.

---

## Email Verification

### Verify Emails
```
POST /v2/email-verification/start          → task_hash
GET  /v2/email-verification/result?task_hash={hash}
```
| Param | Required | Description |
|-------|----------|-------------|
| `emails[]` | Yes | Up to 10 emails |
| `webhook_url` | No | Optional |

**Response fields:** `smtp_status` (`valid`/`not_valid`/`unknown`), `is_valid_format`, `is_disposable`, `is_webmail`, `is_gibberish`, `unknown_status_reason` (`banned`/`catchall`/`connection_error`/`greylist`/`hidden_by_owner`).

---

## Prospect Management

### Add Prospect to List
```
POST /v1/add-prospect-to-list
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `first_name` | Yes | |
| `last_name` | Yes | |
| `email` | Yes | |
| `list_id` | Yes | Integer list ID |
| `custom_fields` | No | Object with custom field values |

### Find Prospect by ID
```
POST /v1/find-prospect-by-id
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `prospect_id` | Yes | Unique prospect identifier |

### Find Prospect by Email
```
POST /v1/find-prospect-by-email
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `email` | Yes | Prospect's email |

### Get Custom Fields
```
GET /v1/get-prospect-custom-fields
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `list_id` | Yes | Prospect list ID |

### List All Prospect Lists
```
GET /v1/get-user-lists
```
**Cost:** FREE. No params. Returns all lists with IDs and names.

### View Prospects in List
```
POST /v1/view-prospects-in-list
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `list_id` | Yes | Integer list ID |
| `offset` | No | Pagination (up to 10,000/request) |

### Create Prospect List
```
POST /v1/create-prospect-list
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `name` | Yes | List name |
| `description` | No | |

---

## Campaign Management

### Get All Campaigns
```
GET /v1/get-user-campaigns
```
**Cost:** FREE. Returns array: `id`, `campaign` name, `list_id`, `status`, `created_at`, `updated_at`, `started_at` (Unix timestamps).

### Campaign Analytics
```
GET /v2/statistics/campaign-analytics
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `campaign_id` | No | Comma-separated IDs |
| `sender_email` | No | Email account ID |
| `sender_linkedin` | No | LinkedIn account ID |
| `campaign_owner` | No | Team member email |
| `date_from` | No | yyyy-mm-dd |
| `date_to` | No | yyyy-mm-dd |

**Response metrics:** `total_contacted`, `emails_sent`, `delivered`, `bounced`, `email_opens`, `email_replies`, `linkedin_total_replies`, `interested`, `maybe`, `not_interested`.

### Campaign Progress
```
GET /v2/campaigns/{campaign_id}/progress
```
**Cost:** FREE. Returns `status`, `unfinished` count, `progress` percentage.

### Change Recipient Status
```
POST /v1/change-recipient-status
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `email` | Yes | |
| `campaign_id` | Yes | |
| `status` | Yes | `Active`/`Paused`/`Unsubscribed` (cannot change `Finished`/`Moved`) |

### Finished Prospects
```
GET /v1/prospect-finished
```
**Cost:** FREE. Param: `campaignId`. Returns `id`, `prospectId`, `userName`, `userEmail`, `campaign`, `hash`.

### Campaign Replies
```
GET /v1/get-emails-replies
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `campaignId` | Yes | |
| `offset` | No | Pagination (up to 10,000/request) |

**Response:** `visitedAt`, `campaignId`, `prospectName`, `prospectEmail`, `emailSubject`, `emailBody`, custom fields.

### Email Opens
```
GET /v1/get-emails-opened
```
**Cost:** FREE. Params: `campaignId`, `offset`. Response: `visitedAt`, `prospectName`, `prospectEmail`, `emailSubject`.

### Link Clicks
```
GET /v1/get-emails-clicked
```
**Cost:** FREE. Params: `campaignId`, `offset`.

### Sent Emails
```
GET /v1/emails-sent
```
**Cost:** FREE. Params: `campaignId`, `offset`. Response: `sentDate`, `userName`, `userEmail`, `campaign`, `hash`, `id`.

### Add to Do-Not-Email List
```
POST /v1/add-to-do-not-email-list
```
**Cost:** FREE.
| Param | Required | Description |
|-------|----------|-------------|
| `email` | Yes | Email to blocklist |

---

## User Account

### Check Balance
```
GET /v1/check-user-balance
```
**Cost:** FREE. Returns current credit balance.

---

## Webhooks

### List Webhooks
```
GET /v2/webhooks
```

### Add Webhook
```
POST /v2/webhooks
```
| Param | Required | Description |
|-------|----------|-------------|
| `url` | Yes | Your webhook endpoint |
| `event` | Yes | Event type to trigger |

### Update Webhook
```
PUT /v2/webhooks/{webhook_id}
```
| Param | Required | Description |
|-------|----------|-------------|
| `status` | Yes | `active`/`inactive` |

### Delete Webhook
```
DELETE /v2/webhooks/{webhook_id}
```

---

## Common Patterns

### Async Task Flow (v2 endpoints)
Most v2 endpoints follow a start/poll pattern:
1. `POST .../start` with params → get `task_hash` from `meta.task_hash`
2. `GET .../result/{task_hash}` → poll until `status` is `done`/`complete`
3. Status values: `in_progress`, `done`, `failed`

### SMTP Status Values
- `valid` — verified deliverable
- `unknown` — unverifiable (catchall, greylisting, etc.)
- `not_valid` — bounces

### Rate Limiting
- 60 req/min global
- On 429: exponential backoff recommended
- Token expires in 3600s, cache it

### Credit Costs Summary
| Endpoint | Cost |
|----------|------|
| Email count check | FREE |
| All prospect management | FREE |
| All campaign endpoints | FREE |
| User balance | FREE |
| Domain search | 1 credit/request |
| Prospect email lookup | 1 credit/email found |
| Email finder by name | 1 credit/email found |
| LinkedIn profile info | 1 credit/profile |
| Profile by email | 1 credit (free if none) |
| Company domain by name | 1 credit/domain found |
| Email verification | Uses verification credits |

---

## Current Integration Status

**Already implemented in `app/services/snov_client.py`:**
- OAuth token management (Redis + in-memory cache)
- `get_domain_email_count()` — `/v1/get-domain-emails-count`
- `search_prospects()` — `/v2/domain-search/prospects/start` + poll
- `search_prospect_email()` — `/v2/domain-search/prospects/search-emails/start/{hash}` + poll
- Rate limiting (1 req/sec throttle)
- Retry logic with exponential backoff on 429/5xx

**Not yet implemented (candidates for email reachout):**
- Email finder by name + domain (`/v2/emails-by-domain-by-name/start`)
- Email verification (`/v2/email-verification/start`)
- LinkedIn profile enrichment (`/v2/li-profiles-by-urls/start`)
- Prospect list management (`/v1/add-prospect-to-list`, `/v1/create-prospect-list`, etc.)
- Campaign management APIs
- Company domain by name (`/v2/company-domain-by-name/start`)
- Profile enrichment by email (`/v1/get-profile-by-email`)
- Webhook registration
