# S4 Email Reveal Design

**Date:** 2026-05-01

## Problem

S3 discovers contacts (Snov + Apollo) and flags them with `title_match`. Operators need to fetch actual email addresses for title-matched contacts so they become usable for outreach.

## Decision

Option A — flat per-contact reveal. One `reveal_email(contact_id)` Procrastinate task per eligible contact. The worker branches on `source_provider` and calls the appropriate provider API.

## Eligibility filter

A contact is eligible for reveal if:
- `title_match=True`
- AND (`email IS NULL` OR `updated_at < now - 30 days`)

Contacts with a fresh email (revealed within 30 days) are counted as `skipped_revealed_count` and no task is deferred.

## Data flow

```
POST /v1/contacts/reveal
  ├─ Input: campaign_id, discovered_contact_ids (explicit selection from UI)
  ├─ Filter to eligible contacts (title_match + email/staleness rule above)
  ├─ Create ContactRevealBatch (selected_count, queued_count, skipped_revealed_count)
  ├─ Defer reveal_email(contact_id) per eligible contact
  └─ Return ContactRevealResult

reveal_email(contact_id) worker
  ├─ Load Contact, branch on source_provider
  ├─ "snov"   → SnovClient.search_prospect_email(provider_person_id)
  │             fallback: find_email_by_name(first_name, last_name, domain)
  ├─ "apollo" → ApolloClient.reveal_email(provider_person_id)
  └─ Write: email, email_provider, email_confidence,
            provider_email_status, reveal_raw_json,
            pipeline_stage → "email_revealed"
```

## Provider mechanics

**Snov:** `search_prospect_email(provider_person_id)` returns `[{email, smtp_status}]`. Pick best email (prefer `smtp_status="valid"` over `"unknown"`). If result is empty, fall back to `find_email_by_name(first_name, last_name, domain)`.

**Apollo:** `reveal_email(provider_person_id)` returns an enriched person dict. Extract `person.get("email")`. Map to `email_confidence=1.0` if present.

**smtp_status → email_confidence mapping:** `valid=1.0`, `unknown=0.5`, anything else `=0.0`.

## Error handling

- **No email returned:** leave `Contact.email` as `None`, `pipeline_stage` unchanged (`"fetched"`). Contact remains eligible for a future reveal.
- **Provider API error:** leave contact untouched; Procrastinate retries up to `max_attempts` with backoff.
- **Unknown source_provider:** log warning, skip silently.

## Files

| File | Action |
|---|---|
| `app/services/email_reveal_service.py` | Create — enqueue logic + `run_reveal(engine, contact_id)` |
| `app/jobs/email_reveal.py` | Modify — replace stub, call service |
| `app/api/routes/contacts.py` | Modify — implement `POST /v1/contacts/reveal` |

## Alternatives considered

- **Option C (batch per company):** Apollo supports batch `reveal_email`; Snov's batch uses name-based lookup (less accurate than hash-based). Rejected for the core pass in favour of simplicity; can be revisited if credit cost becomes a concern.
