# Contact Pipeline Design
**Date:** 2026-03-20
**Status:** Planning — awaiting Snov.io credentials + ZeroBounce key

---

## Overview

Three-phase roadmap after analysis classifies companies:

| Phase | Description | Status |
|-------|-------------|--------|
| STEP 1 | Feedback (thumbs up/down on Companies page) | ✅ Done |
| STEP 2 | Contact fetching via Snov.io + ZeroBounce verification | 🔜 Next |
| STEP 3 | Email campaign engine (mini Instantly/Lemlist, operator's own SMTP) | 📋 Designed |

---

## STEP 1 — Feedback ✅

- Thumbs up / down + optional comment in company Review drawer (Companies page)
- `PUT /v1/companies/{company_id}/feedback`
- `feedback_thumbs` + `feedback_comment` in all company list responses and CSV export

---

## STEP 2 — Contact Fetching

### Decisions

- **Trigger**: Manual only. "Fetch contacts" button per company or bulk per run. API credits are finite.
- **Volume**: ~100–150 `Possible` companies per run
- **Title filter**: Client has provided a list of target job titles; only contacts matching those titles should be surfaced for outreach (others still stored but flagged `title_mismatch`)
- **ZeroBounce**: Key not yet available — build Snov integration first, ZeroBounce slot left wired but skippable (`email_status = "unverified"` if no key)

### Data Model

New table: `ProspectContact`

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| company_id | UUID FK | → Company |
| source | str | `"snov"` |
| first_name | str | |
| last_name | str | |
| title | str | nullable |
| title_match | bool | true if title in client's watchlist |
| email | str | |
| email_status | str | `unverified`, `valid`, `invalid`, `catch_all`, `unknown`, `do_not_mail` |
| snov_confidence | float | Snov's own confidence score (0–1) |
| snov_raw | JSON | full Snov response |
| zerobounce_raw | JSON | full ZeroBounce response, null until verified |
| created_at | datetime | |
| updated_at | datetime | |

New table: `ContactTitleWatchlist`

| Field | Type | Notes |
|-------|------|-------|
| id | UUID | PK |
| title_pattern | str | e.g. "Head of Sales", "Commercial Director" |
| created_at | datetime | |

(Or store as a simple config/JSON if the list is static per client.)

### Pipeline

```
Operator clicks "Fetch contacts" for company or run
  │
  ▼
POST /v1/companies/{id}/fetch-contacts  (or /runs/{id}/fetch-contacts)
  │
  ▼
Celery task: fetch_contacts(company_id)
  │
  ├─► Snov.io domain search → list of {name, title, email, confidence}
  │     Filter by title watchlist → set title_match flag
  │     Save ProspectContact rows (email_status = "unverified")
  │
  └─► ZeroBounce batch verify (if API key present)
        Update email_status per contact
```

### Snov.io Integration

- Auth: OAuth2 client credentials (`POST /v2/oauth/access_token`)
- Search: `POST /v2/domain-emails-with-info` — returns contacts per domain
- Rate limit: ~100 req/min on most plans — throttle via LLMClient-style `min_interval_sec`
- Store `snov_raw` for full auditability

### ZeroBounce Integration

- Endpoint: `POST /v2/validatebatch` (up to 100 emails per call)
- Statuses to keep for outreach: `valid` (safe), optionally `catch_all` (flag with warning)
- Discard: `invalid`, `spamtrap`, `abuse`, `do_not_mail`
- If key absent: skip, leave `email_status = "unverified"` — do not block Snov fetch

### Backend

```
app/services/contact_service.py      # Snov + ZeroBounce logic
app/tasks/contacts.py                # Celery task: fetch_contacts(company_id)
app/api/routes/contacts.py           # REST endpoints
```

API routes:
- `POST /v1/companies/{company_id}/fetch-contacts` — queue fetch for one company
- `POST /v1/runs/{run_id}/fetch-contacts` — bulk queue for all `Possible` in run
- `GET /v1/companies/{company_id}/contacts` — list contacts + status
- `GET /v1/contacts` — global contacts list (for Contacts screen, filterable)
- `POST /v1/contacts/verify` — trigger ZeroBounce re-verify (when key arrives)

### Frontend — two surfaces

**1. Company detail panel — Contacts tab**
- Shows contacts for that company
- Status badges: `valid` (green), `catch_all` (yellow/warning), `unverified` (grey), `invalid` (red strikethrough)
- Title match highlighted
- "Fetch contacts" button when no contacts yet or `Possible`

**2. New: Contacts screen** (top-level nav)
- Filterable table: run, company, title, email_status, title_match
- Bulk actions: verify selected, add to campaign (STEP 3)
- Export verified contacts as CSV

### Companies page additions

- New column: `contacts` — count of valid contacts found (e.g. "3 valid")
- New column: `contact_status` badge — `none`, `fetching`, `fetched`, `verified`
- Action button in row: "Fetch contacts" shortcut

### New env vars

```
PS_SNOV_CLIENT_ID=
PS_SNOV_CLIENT_SECRET=
PS_ZEROBOUNCE_API_KEY=       # optional at first, verify step skipped if absent
```

---

## STEP 3 — Email Campaign Engine

### Vision

A self-hosted mini email sequencer. The operator connects their own email account (SMTP/IMAP) and runs sequences from inside this app. No dependency on Instantly or Lemlist — but export to those stays available.

### Core concepts

| Concept | Description |
|---------|-------------|
| Mailbox | Operator's SMTP/IMAP account credentials (encrypted at rest) |
| Sequence | Named series of email steps (e.g. Day 0 intro, Day 3 follow-up, Day 7 final) |
| Enrollment | A contact enrolled in a sequence — tracks current step + state |
| Thread | Email thread for a contact — reply detection via Message-ID / In-Reply-To headers |

### Data Models (outline)

```
Mailbox          — smtp_host, smtp_port, imap_host, imap_port, email, encrypted_password
Sequence         — name, description, created_at
SequenceStep     — sequence_id, step_index, delay_days, subject_template, body_template
Enrollment       — contact_id, sequence_id, current_step, state, enrolled_at
EmailMessage     — enrollment_id, step_id, message_id (RFC), sent_at, opened_at, replied_at, bounced_at
```

### States per enrollment

```
active → waiting (delay not elapsed) → sending → sent
                                                  ├── replied   (terminal - success)
                                                  ├── bounced   (terminal - remove)
                                                  └── finished  (all steps done, no reply)
```

### Sending engine

- Celery beat checks every N minutes for enrollments where `next_send_at <= now`
- Sends via SMTP, stores `message_id` header
- IMAP poller checks inbox for replies matching known `message_id` / `In-Reply-To` chains
- On reply detected: mark enrollment `replied`, stop further steps

### Key tracking metrics per contact

- Days since first contact
- Days since last response (replied or opened)
- Step number currently on
- Total emails sent / opened / replied

### Reply detection approach

1. IMAP IDLE / polling — scan Sent + Inbox for matching Message-ID threads
2. Match against `EmailMessage.message_id` — if found in a reply, mark `replied_at`
3. No pixel tracking required (avoids spam filters)

### Template personalisation

- Variables: `{{first_name}}`, `{{company}}`, `{{domain}}`, `{{title}}`
- Optionally: LLM-generated first line (icebreaker) using classification reasoning already stored

### Frontend screens

- **Mailboxes** — connect/test SMTP+IMAP account
- **Sequences** — create/edit multi-step sequences with delay + template per step
- **Campaigns** — enroll contacts from Contacts screen into a sequence
- **Inbox monitor** — replies, bounces, out-of-office flags
- **Stats** — sent / open rate / reply rate / bounce rate per sequence

### Phase split

| Phase | Scope |
|-------|-------|
| 3a | Mailbox connect + send single email (prove SMTP works) |
| 3b | Sequences + enrollment engine + beat sender |
| 3c | IMAP reply detection + enrollment state machine |
| 3d | Stats dashboard + icebreaker LLM personalisation |

---

## Build Order

### STEP 2
1. `ContactTitleWatchlist` — define target titles (config or DB table)
2. `ProspectContact` model + Alembic migration
3. `contact_service.py` — Snov OAuth + domain search + title matching
4. Celery task `fetch_contacts` + `contacts` queue wiring in docker-compose
5. API routes (fetch trigger + list)
6. Frontend: Contacts tab in company panel + "Fetch contacts" button
7. New Contacts screen (global list, filterable, bulk actions)
8. Companies page: contacts count column + contact_status badge
9. ZeroBounce verify layer (once key available)
10. CSV export update

### STEP 3
1. Mailbox model + encrypted credential storage
2. SMTP send + test connection endpoint
3. Sequence + SequenceStep models
4. Enrollment model + beat sender task
5. IMAP reply poller
6. Frontend: Mailboxes, Sequences, Campaigns screens
7. Stats dashboard
8. LLM icebreaker (optional, Phase 3d)
