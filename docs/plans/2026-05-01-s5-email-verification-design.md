# S5 Email Verification Design

**Date:** 2026-05-01

## Problem

After S4 reveals email addresses, operators need to verify them before outreach. Sending to invalid or spam-trap addresses hurts deliverability. ZeroBounce provides a batch validation API that classifies emails as valid, invalid, catch-all, unknown, etc.

## Decision

Option B — batch task via `ContactVerifyJob`. The API creates one `ContactVerifyJob` storing all selected contact IDs, defers one `verify_contacts(job_id)` task, and the worker calls `ZeroBounceClient.validate_batch()` once for the entire selection.

## Eligibility filter

Uses existing `verification_eligible_condition()` from `contact_query_service.py`:
- `title_match=True`
- `email IS NOT NULL`
- `verification_status="unverified"`

Contacts not matching are counted as `skipped_count` on the job.

## Data flow

```
POST /v1/contacts/verify
  ├─ Input: campaign_id, contact_ids (explicit selection)
  ├─ Filter through verification_eligible_condition()
  ├─ Create ContactVerifyJob (contact_ids_json, selected_count, skipped_count)
  ├─ Defer verify_contacts(job_id) — one task for the whole batch
  └─ Return ContactVerifyResult(job_id, selected_count, message)

verify_contacts(job_id) worker
  ├─ CAS-claim job (queued → running)
  ├─ Load Contact rows from contact_ids_json
  ├─ Call ZeroBounceClient.validate_batch(emails) — one API call
  ├─ For each result row: write verification_status, verification_provider="zerobounce",
  │                        zerobounce_raw to the Contact
  ├─ If status="valid" AND title_match=True → pipeline_stage="campaign_ready"
  └─ Finalize job: state=succeeded/failed, verified_count, skipped_count, finished_at
```

## Status mapping

ZeroBounce returns `status` per email. Written directly to `Contact.verification_status`:
- `"valid"` → also sets `pipeline_stage="campaign_ready"` if `title_match=True`
- `"invalid"`, `"catch-all"`, `"unknown"`, `"spamtrap"`, `"abuse"`, `"do_not_mail"` → written as-is, `pipeline_stage` unchanged

## Error handling

- **ZeroBounce API error:** leave all contacts untouched, finalize job as `failed`. Procrastinate retries up to `max_attempts`.
- **Individual result malformed (missing `email_address`):** skip that row, continue processing others.
- **Credentials missing:** fail fast with `zerobounce_api_key_missing`, job → `failed`.

## Files

| File | Action |
|---|---|
| `app/services/contact_verify_service.py` | Create — enqueue + `run_verify(engine, job_id)` |
| `app/jobs/validation.py` | Modify — replace stub with `verify_contacts(job_id)` |
| `app/api/routes/contacts.py` | Modify — implement `POST /v1/contacts/verify` |

## What already exists

- `ContactVerifyJob` model with `contact_ids_json`, `selected_count`, `verified_count`, `skipped_count`
- `verification_eligible_condition()` in `contact_query_service.py`
- `ZeroBounceClient.validate_batch(emails)` in `zerobounce_client.py`
- `ContactVerifyRequest` / `ContactVerifyResult` schemas (frontend already wired to `POST /v1/contacts/verify`)
- `validate_email(contact_id)` stub in `app/jobs/validation.py` (to be replaced)
