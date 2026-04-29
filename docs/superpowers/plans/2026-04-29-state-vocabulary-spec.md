# State Vocabulary Specification

**Date:** 2026-04-29
**Status:** Authoritative — every state/stage/label value in the system MUST come from this doc.

## Rules

1. **Lowercase, snake_case.** No `UPPERCASE`, no `Title Case`, no `kebab-case`. Code and DB agree.
2. **`succeeded`, never `completed`.** Completion is ambiguous; success is not.
3. **Field naming by domain:**
   - `state` — for jobs, attempts, runs (anything async with a lifecycle)
   - `pipeline_stage` — for entities (companies, contacts) progressing through the pipeline
   - `verdict` or `label` — for classifications and human decisions
   - `verification_status` — for the result of an external verification call
4. **Failure reasons are NOT states.** A scrape that hits a 503 is `state=failed, failure_reason=site_unavailable`. Never `state=site_unavailable`.
5. **No ordering encoded in enum values.** It's `scrape`, not `s1_scrape`.
6. **Provider raw responses stay as `*_raw_json`.** Normalize into our vocabulary before storing in any state/status column.
7. **Adding a new value requires updating this doc first.** PRs that introduce undeclared values get rejected.

---

## Entity Pipeline Stages

### `companies.pipeline_stage`
| Value | Meaning |
|-------|---------|
| `uploaded` | Row exists, no scrape attempted yet |
| `scraped` | Scrape succeeded, no AI classification yet |
| `classified` | AI classification done, result is `crap` or `unknown` |
| `contact_ready` | AI classification done, result is `possible` (or human override) — eligible for contact fetch |

**No migration needed** — values already lowercase in DB.

### `contacts.pipeline_stage`
| Value | Meaning |
|-------|---------|
| `fetched` | Contact discovered by fetch job, no email yet |
| `email_revealed` | Email obtained from provider, not yet verified |
| `verification_ran` | ZeroBounce called, result in `verification_status` (regardless of result value) |
| `campaign_ready` | `verification_ran` + `verification_status in (valid, catch_all)` + `title_match=true` |

**Migration:** all current rows are `fetched`. Future rows transition through stages as the pipeline runs.

---

## Verification

### `contacts.verification_status`
| Value | Meaning |
|-------|---------|
| `unverified` | ZeroBounce has not been called for this contact |
| `valid` | Confirmed deliverable |
| `invalid` | Confirmed undeliverable |
| `catch_all` | Domain accepts all email — deliverability uncertain but plausible |
| `unknown` | ZeroBounce returned uncertain result |
| `spamtrap` | Known spamtrap address |
| `abuse` | Known abuse address |
| `do_not_mail` | On a do-not-mail list |

**Migration:** all current rows are `unverified`. ZeroBounce raw response → mapped via service code into one of these.

### `contacts.verification_provider` (new column)
| Value | Meaning |
|-------|---------|
| `zerobounce` | Verified by ZeroBounce |
| `null` | Not verified yet |

---

## Job, Attempt, and Run States

**Single canonical state vocabulary used by every async lifecycle column.**

### Allowed values
| Value | Meaning |
|-------|---------|
| `created` | Row inserted but not yet visible to a worker (rare — usually used when work is conditional) |
| `queued` | Available for a worker to pick up |
| `running` | A worker has claimed it and is executing |
| `paused` | Manually paused — workers will not pick up |
| `deferred` | Worker decided to retry later (e.g., rate limit, transient error) |
| `succeeded` | Completed successfully |
| `failed` | Completed unsuccessfully (recoverable — may be retried) |
| `cancelled` | Manually cancelled before completion |
| `dead` | Permanently failed, no further retries (max attempts reached or non-recoverable) |

### Tables using this vocabulary
After migration, the following columns ALL use the values above:

- `scrapejob.state` (renamed from `status`)
- `crawl_jobs.state`
- `analysis_jobs.state`
- `contact_fetch_jobs.state`
- `contact_fetch_batches.state`
- `contact_provider_attempts.state`
- `contact_reveal_jobs.state`
- `contact_reveal_batches.state`
- `contact_reveal_attempts.state`
- `contact_verify_jobs.state`
- `pipeline_runs.state` (renamed from `status`)

### Migration from current values
| Current | New |
|---------|-----|
| `SUCCEEDED` (uppercase, in `crawl_jobs`, `analysis_jobs`) | `succeeded` |
| `FAILED` | `failed` |
| `DEAD` | `dead` |
| `completed` (in `scrapejob.status`, `contact_fetch_batches.state`) | `succeeded` |
| `cancelled` | `cancelled` (no change) |
| `site_unavailable` (in `scrapejob.status`) | `state=failed, failure_reason=site_unavailable` |
| `step1_failed` (in `scrapejob.status`) | `state=failed, failure_reason=step1_failed` |
| `running` (8 stuck rows in `pipeline_runs.status`) | `dead` |

---

## Failure Reasons

### `*.failure_reason` — separate column, populated only when `state=failed` or `state=dead`
| Value | Meaning |
|-------|---------|
| `site_unavailable` | Target site returned 5xx or connection refused |
| `step1_failed` | First step of multi-step scrape failed |
| `circuit_open` | Provider circuit breaker tripped |
| `timeout` | Operation exceeded time budget |
| `blocked` | Target detected automation, blocked the request |
| `unknown` | Failure mode not classified (catch-all) |
| `null` | Not failed (state is not `failed` or `dead`) |

**Tables that gain a `failure_reason` column:**
- `scrapejob`
- `crawl_jobs`
- `contact_fetch_jobs`
- `contact_provider_attempts`
- `contact_reveal_attempts`

`null` is the only valid value when `state NOT IN (failed, dead)`.

---

## Classification Labels

### `classification_results.predicted_label`
| Value | Meaning |
|-------|---------|
| `possible` | AI says this is a viable prospect |
| `crap` | AI says this is not a viable prospect |
| `unknown` | AI could not determine |

**Migration:** rewrite `POSSIBLE` → `possible`, `CRAP` → `crap`, `UNKNOWN` → `unknown` in existing rows.

### `company_feedback.manual_label`
| Value | Meaning |
|-------|---------|
| `possible` | Human override: this IS a viable prospect |
| `crap` | Human override: this is NOT a viable prospect |
| `unknown` | Human override: result is unclear |
| `null` | No human feedback |

When `manual_label IS NOT NULL`, it overrides `predicted_label` for all downstream filtering.

---

## Provider Enums

### `contacts.source_provider` (renamed from `provider`)
| Value | Meaning |
|-------|---------|
| `snov` | Contact discovered via Snov.io |
| `apollo` | Contact discovered via Apollo |

### `contacts.email_provider`
| Value | Meaning |
|-------|---------|
| `snov` | Email revealed via Snov.io |
| `apollo` | Email revealed via Apollo |
| `null` | Email not yet revealed |

(Allows for "discovered by Snov, revealed by Apollo" cross-provider scenarios.)

### `contacts.verification_provider`
See Verification section above.

---

## Title Matching

### `title_match_rules.rule_type`
| Value | Meaning |
|-------|---------|
| `include` | All keywords in this rule must appear in the title (AND) |
| `exclude` | Any keyword in this rule disqualifies the title (any-of-many) |

Multiple include rules are OR'd together. Exclude rules are evaluated before includes.

### `title_match_rules.match_type`
| Value | Meaning |
|-------|---------|
| `keyword` | Substring match against the title |
| `regex` | Regex pattern match |
| `seniority` | Named seniority preset (`c_level`, `vp_level`, `director_level`, `manager_level`, `senior_ic`) |

---

## Pipeline Steps

### `PipelineStage` enum (used by `pipeline_runs`, task routing)
| Value | Meaning |
|-------|---------|
| `scrape` | Scraping stage |
| `analysis` | AI classification stage |
| `contacts` | Contact fetch + reveal stage |
| `validation` | Email verification stage |

**Migration:** rewrite `s1_scrape` → `scrape`, `s2_analysis` → `analysis`, `s3_contacts` → `contacts`, `s4_validation` → `validation`.

---

## Scrape/Fetch Mode

### `scrapejob.scrape_mode` (or wherever the mode is stored)
| Value | Meaning |
|-------|---------|
| `none` | No scrape attempted |
| `static` | Plain HTTP fetch, no JS |
| `static_thin` | Static fetch with minimal payload (HEAD-like) |
| `impersonate` | Browser impersonation, no JS execution |
| `stealth` | Stealth headless browser |
| `dynamic` | Full headless browser with JS |

---

## Quick Reference — What Changes Per Table

| Table | Column changes |
|-------|----------------|
| `companies` | None |
| `contacts` | Rename `provider` → `source_provider`. Add `verification_provider`. |
| `classification_results` | Lowercase `predicted_label` values |
| `company_feedback` | None (already lowercase) |
| `scrapejob` | Rename `status` → `state`. Add `failure_reason`. Migrate values. |
| `crawl_jobs` | Lowercase `state` values |
| `analysis_jobs` | Lowercase `state` values |
| `contact_fetch_jobs` | Add `failure_reason`. Already lowercase. |
| `contact_provider_attempts` | Add `failure_reason`. Already lowercase. |
| `contact_reveal_jobs` | (No change — already lowercase, no failure_reason needed yet) |
| `contact_reveal_attempts` | Add `failure_reason`. Already lowercase. |
| `contact_verify_jobs` | (No change) |
| `pipeline_runs` | Rename `status` → `state`. Migrate 8 stuck `running` rows to `dead`. |
| `runs` | Drop entirely after Phase 1 verifies `pipeline_runs` is the only consumer. |
