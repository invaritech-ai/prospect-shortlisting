# S3/S4 Email Pipeline Direction

**Status:** Directional spec, awaiting mini implementation plans.

**Date:** 2026-05-16

**Goal:** Replace the current S3-S5 contact/reveal/validation model with a simpler operator-controlled S3 Email Fetch and S4 Email Verification model.

**Decision owner:** Avi.

---

## Core Direction

S1 Scraping and S2 AI Decision stay as they are.

The post-S2 pipeline becomes:

| Stage | Product name | Purpose |
|---|---|---|
| S3 | Email Fetch | Find role/title-matched people for selected companies and fetch their emails through Apollo first, then Snov fallback. |
| S4 | Email Verification | Verify fetched email snapshots through ZeroBounce and promote only valid emails to campaign-ready. |

Old standalone S4 Retry Reveals and S5 Validation are removed from the product model. Broken endpoints, obsolete views, stale tests, old frontend mappings, and old stage concepts can be removed rather than preserved.

This is a breaking cleanup. There is no requirement to preserve historical S5 validation data.

## Operator Control

The system should remain operator-controlled.

S3 runs only when the operator selects companies and triggers email fetch. S4 runs only when the operator selects eligible emails or companies and triggers verification.

No implementation starts until Avi approves a written mini plan. After the direction spec is approved, the work proceeds through mini implementation plans with explicit checkpoints.

Priority order:

1. Reliability.
2. Accuracy.
3. UX.
4. Speed.

## Provider Model

S3 should feel like one action to the operator: fetch emails using the current role/title criteria.

Internal provider flow:

1. Apollo: search people by company domain and role/title criteria.
2. Apollo: bulk email enrichment/fetch for the top matched candidates.
3. Stop if Apollo returns at least one usable title-matched email.
4. If Apollo is unavailable or returns zero usable emails, use Snov fallback.
5. Snov: prospect search by domain and positions/title criteria.
6. Snov: per-prospect email fetch for top matched candidates.
7. Store results to the database incrementally with idempotent upserts.

Apollo and Snov complexity must be hidden behind a simple internal provider API. Pipeline orchestration should not know about Apollo endpoint names, Snov task hashes, polling details, placeholder emails, or provider response shapes.

S4 uses ZeroBounce for email verification.

Relevant provider docs:

- Apollo People Search: `https://docs.apollo.io/reference/people-api-search`
- Apollo People Enrichment: `https://docs.apollo.io/reference/people-enrichment`
- Snov API: `https://snov.io/api`
- ZeroBounce validation: `https://www.zerobounce.net/docs/email-validation-api-quickstart/`

## Simplified Internal API

S3 orchestration should call a simple adapter boundary shaped around product intent:

```python
provider.fetch_target_emails(
    domain=domain,
    criteria=criteria_snapshot,
    candidate_cap=5,
) -> ProviderEmailFetchResult
```

The result should contain normalized data, not raw provider-specific shapes:

- contacts with fetched emails
- role-matched people with no email found
- logical attempt summaries
- provider error codes
- provider evidence ids or compact raw summaries

The provider adapters translate local criteria into provider-side filters where possible, but local matching remains the source of truth.

## Criteria Snapshots And Hashing

Each S3 job stores a criteria snapshot at enqueue time. If campaign criteria changes while jobs are queued or after contacts are fetched, old contacts remain visible.

Snapshot should include:

- campaign id
- include title rules
- exclude title rules or words
- candidate cap
- provider order
- fallback rule
- timestamp/version

Use a deterministic criteria hash for cheap comparison. Store both:

- full criteria snapshot JSON for debugging
- canonical hash for equality/filter checks

The comparison hash should represent targeting criteria only. Provider order and caps affect how the fetch was run, but not who the campaign is trying to target. Store provider order and caps in the snapshot, but do not include them in the targeting hash.

UI should show a lightweight `Criteria changed` or equivalent marker when a contact was last touched under an older criteria hash.

## Matching Rules

Title/role matching should happen both before and after paid email fetch.

Provider-side filters are useful for cost control but are not the contract. A shared local matcher is the source of truth and should be used by:

- S3 orchestration
- Apollo adapter
- Snov adapter
- tests
- any relevant UI preview logic when practical

Before email fetch, candidates are ranked and capped.

Default candidate cap: 5 title-matched candidates per company per provider attempt.

Default ranking:

1. Strongest campaign title-rule match.
2. Exact title phrase match.
3. Seniority fit.
4. LinkedIn URL present.
5. Provider confidence/completeness.
6. Stable provider order.

## Data Model Principles

Keep the model semi-normalized. Fetching normal operational data should be at most two hops away, meaning no more than three table joins in common paths.

`Contact` remains the main person/contact table and stores both:

- people with fetched emails
- role-matched people where no email was found

Do not split source of truth unnecessarily across prospect, email lookup, provider identity, and contact tables unless a future mini plan proves the need.

Recommended shape:

- `Contact` remains.
- Rename S3 job concepts from `ContactFetchJob` to `EmailFetchJob`.
- Rename S4 verification job concepts from `ContactVerifyJob` to `EmailVerificationJob`.
- Keep canonical fields on `Contact`.
- Add or adapt evidence JSON on `Contact` for multi-provider evidence.
- Use append-only logical provider attempt rows for S3 internals.

`Contact` should support canonical provider fields plus multi-provider evidence:

- `source_provider`: provider that first created or most confidently identified the person
- `email_provider`: provider that supplied the current email
- `provider_person_id`: canonical provider id for `source_provider`
- `provider_evidence_json`: compact map of Apollo/Snov evidence

## Attempts And Evidence

Do not persist every HTTP retry, Snov poll, or per-request transport event as its own provider-attempt row.

Persist append-only logical attempts. A logical attempt is something the operator or developer can understand:

- `apollo_search`
- `apollo_email_fetch`
- `snov_prospect_search`
- `snov_email_fetch`
- `zerobounce_validation`

Each logical attempt should summarize:

- provider
- operation
- sequence index
- state
- error code/message
- requested count
- result count
- email count
- provider task ids/request ids
- duration
- retry/poll counters
- compact raw summary JSON
- credit/cost estimate when reliable

Transport-level retries and polls belong in counters, compact JSON, or logs.

## Contact Upserts And Merging

S3 writes contacts incrementally as provider results become available. If Apollo stores useful data and Snov later fails, Apollo results remain.

Deduplicate into one canonical contact when confidence is high:

1. Same normalized email within the same company.
2. Same LinkedIn URL within the same company.
3. Same provider and provider person id.
4. Same first name, last name, and company as a cautious fallback.

If Apollo finds the person and Snov finds the email, merge into one `Contact` row. Keep provider evidence for both.

Do not delete or downgrade contacts by default on later runs.

If a later run sees the same contact:

- update `last_seen_at`
- update title/name/LinkedIn only when the new data is better
- append evidence
- update email only when a better/current email is found
- reset verification to unverified if the current email changes

If a later run does not find the contact/email, mark it stale by freshness metadata. Do not clear the email or validation result just because a provider missed it.

Freshness fields to consider:

- `last_seen_at`
- `last_email_seen_at`
- `stale_after_days`, default 30

UI label should use `Stale`, not `Not found`, because provider absence is not proof of invalidity.

## S3 Success Semantics

S3 company-level job success should separate operational truth from business usefulness.

Recommended outcomes:

- `no_matches`: providers worked, no title-matched people found
- `contacts_no_email`: title-matched people found, no usable email fetched
- `email_success`: at least one title-matched email fetched
- `partial_success`: one provider produced useful data and another failed
- `provider_failed`: all attempted providers failed before useful data was produced

A company-level S3 job succeeds operationally if it stores at least one title-matched contact row, even if no email was found. It is email-successful only if at least one title-matched contact has a usable email.

## S3 Retry

Keep retry as an action inside S3, not as a separate stage.

Retry operates at company level only. The operator selects companies and triggers S3 again using the current criteria snapshot. Retry does not clear old contacts. It appends new logical attempts, updates freshness/evidence, and merges contacts.

Do not add individual-contact retry for now. That would leak provider-specific identity complexity back into the product model.

## S4 Verification

S4 verifies emails, not people.

The user can select emails directly, or select companies and let the UI/backend expand them to eligible fetched emails.

The backend job input should store email snapshots:

```json
[
  { "contact_id": "...", "email": "person@example.com" }
]
```

The worker verifies the exact enqueue-time email. On writeback, apply the result only if the contact still has that same email. If the contact email changed, mark that verification item skipped/stale and leave the contact unverified.

Only ZeroBounce `valid` promotes a contact to campaign-ready.

Other statuses remain stored but not ready:

- `catch_all`
- `unknown`
- `do_not_mail`
- `spamtrap`
- `abuse`
- `invalid`

No manual override for non-valid statuses in the first cleanup.

## Verification Cache

ZeroBounce results can be reused globally across campaigns.

Rules:

- Normalize email to lowercase.
- Reuse a fresh ZeroBounce result for the same normalized email.
- Default freshness window: 30 days.
- Record whether the result came from a fresh API call or cache.
- A future force-reverify action can bypass cache.

Initial implementation can query existing contact verification results by normalized email if that keeps the schema simple. A dedicated `email_verifications` table can be introduced later only if needed.

## Queue And Jobs

Keep Procrastinate.

S3 remains one queue job per company. Do not split Apollo search, Apollo enrichment, Snov search, and Snov email fetch into separate queue jobs for now.

S3 worker shape:

```text
fetch_company_target_emails(company_id, campaign_id, criteria_snapshot)
  -> Apollo search
  -> Apollo bulk email fetch
  -> stop if usable email
  -> otherwise Snov prospect search
  -> Snov email fetch
  -> incremental contact upserts
  -> logical attempt summaries
```

S4 queue jobs operate on email snapshots, not company records.

Automatic retry should be limited to transient provider/system failures:

- rate limit
- timeout
- 5xx
- temporary network failure
- token refresh race

Do not automatically retry business outcomes:

- no title criteria
- no prospects found
- prospects found but no email
- credential/auth failure after clear detection
- insufficient credits

These should surface to the operator.

## API And Frontend Naming

Use breaking API names now.

Suggested endpoints:

- `POST /v1/email-fetch-jobs`
- `GET /v1/email-fetch-jobs/{id}`
- `POST /v1/email-verification-jobs`
- `GET /v1/email-verification-jobs/{id}`

Remove old `/contacts/reveal` and old S5 validation-specific endpoints if they only support the obsolete model.

Frontend product labels:

- S3: `Email Fetch`
- S4: `Email Verification`

Remove old `Retry Reveals` as a stage. Remove S5 from navigation, stage mappings, and product UI.

Frontend implementation should be minimal first:

1. Convert current S3 view to Email Fetch.
2. Remove old S4 Retry Reveals view.
3. Convert current S5 Validation view into S4 Email Verification.
4. Update sidebar, bottom nav, API client, types, filters, and status labels.
5. Let build/lint identify dead frontend pieces to remove.

## Testing Posture

Use focused backend service/API tests around changed behavior, plus frontend build.

Minimum tests:

- Apollo success stops before Snov.
- Apollo no usable email falls back to Snov.
- Apollo unavailable falls back to Snov.
- No-email candidates are stored.
- Apollo/Snov duplicate people merge.
- Criteria snapshot/hash is stable.
- Criteria stale marker is derivable.
- S3 writes incrementally when fallback partially fails.
- S4 verifies enqueue-time email snapshot.
- S4 skips writeback when contact email changed.
- S4 reuses fresh cached ZeroBounce result.
- Only `valid` promotes to campaign-ready.
- Obsolete reveal/S5 endpoints are gone.
- Frontend build passes after removing old S4/S5 model.

## Mini Plan Sequence

Implementation should happen as one branch with staged commits/checkpoints, but each mini plan must be approved before code changes.

Recommended mini plans:

1. **Schema and naming foundation**
   - Introduce/rename Email Fetch and Email Verification model concepts.
   - Add criteria snapshots/hash fields.
   - Make S3 logical attempts append-only.
   - Remove old reveal/S5 schema concepts where safe.

2. **Provider adapter API**
   - Define normalized provider result types.
   - Hide Apollo search/enrichment details.
   - Hide Snov prospect/email task details.
   - Add local matcher integration and candidate ranking/cap.

3. **S3 Email Fetch orchestration**
   - Apollo-first waterfall.
   - Snov fallback only when Apollo has zero usable emails or is unavailable.
   - Incremental upserts.
   - Merge/dedupe behavior.
   - Freshness/evidence updates.

4. **S4 Email Verification**
   - Email snapshot job input.
   - ZeroBounce verification.
   - Global fresh-result cache reuse.
   - Valid-only promotion.

5. **API cleanup**
   - Add new breaking endpoints.
   - Remove old reveal/S5 endpoints.
   - Update schemas.
   - Update tests.

6. **Frontend cleanup**
   - Rename S3/S4 UI.
   - Remove S5 navigation.
   - Convert old S5 validation view into S4 verification.
   - Remove retry reveal stage.
   - Add criteria-stale/freshness/provider evidence display.

7. **End-to-end verification**
   - Backend affected tests.
   - Frontend build/lint.
   - Local smoke test with mocked or controlled providers.
   - Manual checklist for operator flow.

## Approval Checkpoints

No code changes should begin until Avi approves the relevant mini plan.

Each mini plan should include:

- exact files to create/modify/delete
- schema migration strategy
- test cases
- expected failing tests before implementation
- implementation steps
- verification commands
- rollback concerns

After each checkpoint:

- summarize diff
- summarize tests run
- call out broken/removed endpoints or frontend views
- ask for approval before moving to the next mini plan

## Non-Goals

- Do not replace Procrastinate.
- Do not preserve old S5 product semantics.
- Do not add manual override for risky ZeroBounce statuses yet.
- Do not add individual-contact S3 retry yet.
- Do not build an accounting-grade provider-cost system yet.
- Do not split the contact source of truth across many normalized provider identity tables unless a mini plan proves it is necessary.

