# ZeroBounce API Reference

> Complete API reference for ZeroBounce email validation, finder, domain search, and scoring.
> Authentication: API key passed as `api_key` query/body parameter.
> Rate limit: **80,000 requests/hour** (200 bad API key requests/hour triggers 1-hour block).

---

## Regional Base URLs

| Region | Validation API | Bulk API |
|--------|---------------|----------|
| Global (default) | `https://api.zerobounce.net` | `https://bulkapi.zerobounce.net` |
| USA | `https://api-us.zerobounce.net` | — |
| EU | `https://api-eu.zerobounce.net` | — |

---

## Email Validation

### Single Email Validation (Real-Time)
```
GET /v2/validate
```
**Cost:** 1 credit (0 credits for `unknown` results).

| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `email` | Yes | Email to validate |
| `ip_address` | No | IP the email signed up from |
| `timeout` | No | 3-60 seconds (returns unknown if exceeded) |
| `activity_data` | No | `true`/`false` — append activity data |
| `verify_plus` | No | `true`/`false` — use Verify+ method |

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | Email validated |
| `status` | string | `valid`, `invalid`, `catch-all`, `unknown`, `spamtrap`, `abuse`, `do_not_mail` |
| `sub_status` | string | Detailed reason (see Status Codes below) |
| `account` | string | Part before `@` |
| `domain` | string | Part after `@` |
| `did_you_mean` | string/null | Typo suggestion |
| `domain_age_days` | string/null | Domain age in days |
| `active_in_days` | string | Last activity: `30`/`60`/`90`/`180`/`365`/`365+` |
| `free_email` | bool | Free email provider |
| `mx_found` | bool | MX record exists |
| `mx_record` | string | Preferred MX record |
| `smtp_provider` | string/null | SMTP provider (BETA) |
| `firstname` | string/null | Owner first name |
| `lastname` | string/null | Owner last name |
| `gender` | string/null | Owner gender |
| `city` | string/null | IP geolocation city |
| `region` | string/null | IP geolocation region |
| `zipcode` | string/null | IP geolocation zip |
| `country` | string/null | IP geolocation country |
| `processed_at` | string | UTC timestamp |

### Batch Email Validation (Real-Time)
```
POST /v2/validatebatch
```
| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `email_batch` | Yes | Array of `{email_address, ip_address}` objects |
| `timeout` | No | 10-120 seconds |
| `activity_data` | No | `true`/`false` |
| `verify_plus` | No | `true`/`false` |

**Response:** Array of validation results (same fields as single validation). Up to 70 seconds response time.

---

## Bulk File Validation

### Send File
```
POST https://bulkapi.zerobounce.net/v2/sendfile
Content-Type: multipart/form-data
```
| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `file` | Yes | CSV or TXT file |
| `email_address_column` | Yes | Column index (starts at 1) |
| `return_url` | No | Callback URL on completion |
| `first_name_column` | No | Column index |
| `last_name_column` | No | Column index |
| `gender_column` | No | Column index |
| `ip_address_column` | No | Column index |
| `has_header_row` | No | `true`/`false` |

**Response:** `{success, message, file_name, file_id}`

### File Status
```
GET https://bulkapi.zerobounce.net/v2/filestatus?api_key={key}&file_id={id}
```
**Response:** `{success, file_id, file_name, upload_date, file_status, complete_percentage}`

### Get File (Download Results)
```
GET https://bulkapi.zerobounce.net/v2/getfile?api_key={key}&file_id={id}
```
**Response:** Binary file download (`application/octet-stream`).

### Delete File
```
GET https://bulkapi.zerobounce.net/v2/deletefile?api_key={key}&file_id={id}
```
File must have `Complete` status before deletion.

---

## Email Finder

### Single Email Finder
```
GET /v2/guessformat
```
**Cost:** 1 subscription query or 20 credits per successful lookup (0 for undetermined).

| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `domain` | Yes* | Email domain |
| `company_name` | Yes* | Company name (*at least one of domain/company_name required) |
| `first_name` | No | Person's first name |
| `middle_name` | No | Person's middle name |
| `last_name` | No | Person's last name |

**Response fields:**

| Field | Description |
|-------|-------------|
| `email` | Found email address |
| `email_confidence` | `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN` |
| `domain` | Domain searched |
| `company_name` | Associated company |
| `format` | Email format pattern (e.g. `{first}.{last}`) |
| `other_domain_formats` | Alternative formats with confidence levels |
| `did_you_mean` | Name correction suggestion |
| `failure_reason` | Reason for unknown result |

### Bulk Email Finder (File Upload)
```
POST https://api.zerobounce.net/email-finder/sendfile
Content-Type: multipart/form-data
```
**Cost:** 20 credits or 1 subscription query per successful match.

| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `file` | Yes | CSV or TXT file |
| `domain_column` | Yes | Column index (starts at 1) |
| `first_name_column` | Yes* | Column index (*or `full_name_column`) |
| `full_name_column` | Yes* | Column index (*or `first_name_column`) |
| `last_name_column` | No | Column index |
| `middle_name_column` | No | Column index |
| `has_header_row` | No | Boolean |

**Response:** `{success, message, file_name, file_id}`

### Bulk Finder - File Status
```
GET https://api.zerobounce.net/email-finder/filestatus?api_key={key}&file_id={id}
```

### Bulk Finder - Get File
```
GET https://api.zerobounce.net/email-finder/getfile?api_key={key}&file_id={id}
```

### Bulk Finder - Delete File
```
GET https://api.zerobounce.net/email-finder/deletefile?api_key={key}&file_id={id}
```
File must be `Complete` before deletion.

---

## Domain Search

### Guess Email Format
```
GET /v2/guessformat
```
Same endpoint as Email Finder — when called with only `domain`/`company_name` (no name fields), returns the domain's email format pattern.

**Response fields:**

| Field | Description |
|-------|-------------|
| `domain` | Domain searched |
| `company_name` | Associated company |
| `format` | Email pattern (e.g. `{first}.{last}@domain.com`) |
| `confidence` | `LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` |
| `other_domain_formats` | Alternative formats with confidence |

### Bulk Domain Search (File Upload)
Same pattern as bulk email finder:
```
POST https://api.zerobounce.net/email-finder/sendfile   (domain search variant)
GET  .../email-finder/filestatus
GET  .../email-finder/getfile
GET  .../email-finder/deletefile
```

---

## AI Scoring

### Single Email Scoring
```
GET /v2/scoring
```
**Cost:** 1 credit per email.

| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `email` | Yes | Email to score |

### Bulk AI Scoring (File Upload)
```
POST https://bulkapi.zerobounce.net/v2/scoring/sendfile
Content-Type: multipart/form-data
```
**Cost:** 1 credit per email.

| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `file` | Yes | CSV or TXT |
| `email_address_column` | Yes | Column index (starts at 1) |
| `return_url` | Yes | Callback URL |
| `has_header_row` | Yes | Boolean |
| `remove_duplicate` | No | Boolean (default: true) |

### AI Scoring - File Status
```
GET https://bulkapi.zerobounce.net/v2/scoring/filestatus?api_key={key}&file_id={id}
```

### AI Scoring - Get File
```
GET https://bulkapi.zerobounce.net/v2/scoring/getfile?api_key={key}&file_id={id}
```

### AI Scoring - Delete File
```
GET https://bulkapi.zerobounce.net/v2/scoring/deletefile?api_key={key}&file_id={id}
```

---

## Activity Data

### Check Email Activity
```
GET /v2/activity
```
| Param | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | API key |
| `email` | Yes | Email to check |

**Response:** `{found: bool, active_in_days: "30"/"60"/"90"/"180"/"365"/"365+"}` — inbox activity in last N days.

---

## Account

### Get Credit Balance
```
GET /v2/getcredits?api_key={key}
```
**Cost:** FREE. Returns `{Credits: number}` (-1 = invalid key).

### Get API Usage
```
GET /v2/getapiusage
```
Returns usage statistics for your account.

---

## Status Codes Reference

### Primary Statuses

| Status | Description |
|--------|-------------|
| `valid` | Safe to email |
| `invalid` | Do not email |
| `catch-all` | Domain accepts all — cannot fully verify |
| `unknown` | Could not validate |
| `spamtrap` | Known spam trap — never email |
| `abuse` | Known complainers — avoid |
| `do_not_mail` | Role-based or disposable — skip |

### Sub-Statuses

**Valid sub-statuses:**
| Sub-status | Description |
|------------|-------------|
| `alias_address` | Forwarder/alias, not a real inbox |
| `leading_period_removed` | Gmail leading period corrected |
| `alternate` | Valid but likely secondary address |
| `gold` | Most active and valuable recipients |
| `role_based_accept_all` | Role-based on catch-all domain, in ZB accept list |
| `accept_all` | Domain configured to accept any recipient |

**Invalid sub-statuses:**
| Sub-status | Description |
|------------|-------------|
| `does_not_accept_mail` | Domain only sends, doesn't receive |
| `failed_syntax_check` | Fails RFC syntax |
| `possible_typo` | Common misspelling of popular domain |
| `mailbox_not_found` | Valid syntax but doesn't exist |
| `no_dns_entries` | No or incomplete DNS records |
| `mailbox_quota_exceeded` | Storage capacity exceeded (temporary) |
| `unroutable_ip_address` | Domain points to unroutable IP |

**Do_not_mail sub-statuses:**
| Sub-status | Description |
|------------|-------------|
| `role_based` | Position/group email (sales@, info@) |
| `disposable` | Temporary email, expires |
| `role_based_catch_all` | Role-based on catch-all domain |
| `mx_forward` | Domain forwards MX records |
| `global_suppression` | On global suppression lists |
| `possible_trap` | Keywords correlating to spam traps |
| `toxic` | Known for abuse/spam, bot-created |

**Unknown sub-statuses:**
| Sub-status | Description |
|------------|-------------|
| `antispam_system` | Anti-spam prevents validation |
| `exception_occurred` | Validation exception |
| `failed_smtp_connection` | SMTP connection refused |
| `forcible_disconnect` | Server disconnects immediately |
| `greylisted` | Temporary greylisting |
| `mail_server_did_not_respond` | Server unresponsive |
| `mail_server_temporary_error` | Server temporary error |
| `timeout_exceeded` | Slow responding mail server |

---

## Credit Costs Summary

| Endpoint | Cost |
|----------|------|
| Get credits / API usage | FREE |
| Single validate (valid/invalid result) | 1 credit |
| Single validate (unknown result) | 0 credits |
| Batch validate | 1 credit per email |
| Bulk file validation | 1 credit per email |
| Single email finder (found) | 20 credits or 1 subscription query |
| Single email finder (undetermined) | 0 credits |
| Bulk email finder (per match) | 20 credits or 1 subscription query |
| AI scoring | 1 credit per email |
| Activity data | Included with validation |
