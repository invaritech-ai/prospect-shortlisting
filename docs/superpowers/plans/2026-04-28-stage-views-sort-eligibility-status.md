# Stage views: domain vs MRU sort, eligibility, status bar — implementation plan

> **For agentic workers:** Use subagent-driven-development (recommended) or executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Implement the agreed UX for **S1 through S5**: full eligible lists sorted **by domain ascending** until that stage has “started”, then switch default to **most-recent stage activity first**, without breaking **stage eligibility rules**. Add a thin **queue status strip** driven by **`GET /v1/stats`** (existing poll in `App.tsx`).

**Architecture:** Treat “started” as a **cheap boolean from `StatsResponse`** per stage (queue or completed work counts). Encode **who belongs on each stage screen** in **API filters and `getPipelineCompanyQuery`** (already uses `has_scrape` for S2). Extend **`list_companies` sort keys** where the grain is companies (S1 to S3). For **S4 and S5** the grain is **person rows** (DiscoveredContact / ProspectContact): use **existing** `domain` versus **recency fields** (`last_seen_at`, `updated_at`) plus optional **`/stats`** fields for reveal/validation so the UI can flip default sort reliably. No new duplicate “five domain tables” unless a later migrations project appears: **one source of truth stays in existing job and contact tables.**

**Tech stack:** FastAPI, SQLModel, React 18, TypeScript, existing `usePipelineViews` loaders.

---

## Locked product rules

| Stage | Row grain | Who appears (eligibility) | Before “started” default sort | After “started” default sort | “Started” signal (v1) |
|-------|-----------|---------------------------|--------------------------------|------------------------------|------------------------|
| **S1** | Company | All companies in campaign | `domain` asc | `scrape_updated_at` desc | `stats.scrape` has any running, queued, completed, failed, site_unavailable, or stuck |
| **S2** | Company | Only companies with scrape data | `domain` asc | `analysis_updated_at` desc | `stats.analysis` non-idle by same pattern |
| **S3** | Company | All companies (contact fetch allowed for any) | `domain` asc | `contact_fetch_updated_at` desc | `stats.contact_fetch` non-idle |
| **S4** | Discovered person | People from contact fetch (discovered list); reveal targets those rows | `domain` asc | Recency (see Task 4) | `stats.contact_reveal` non-idle **or** Phase 2 proxy |
| **S5** | `ProspectContact` in DB | Only stored contacts (validation runs on DB emails) | `domain` asc | `updated_at` desc (already close) | `stats.validation` non-idle |

**Note:** S2 eligibility already matches `apps/web/src/lib/pipelineQuery.ts` (`'s2-ai': 'has_scrape'`). Keep that.

---

## File map

| File | Role |
|------|------|
| `apps/web/src/lib/stageViewSort.ts` | **New.** Pure helpers: `stageStarted*`, `defaultCompanyListSort`, `defaultDiscoveredSort`, `defaultValidationContactSort`. |
| `apps/web/src/hooks/usePipelineViews.ts` | Accept **`stats: StatsResponse | null`** from **`App.tsx`**. Apply default sort on view load and when **stats** flips “started”, unless user changed sort. |
| `apps/web/src/App.tsx` | Pass **`stats`** into **`usePipelineViews`**. |
| `apps/web/src/lib/api.ts` | Pass new `sort_by` strings for `listCompanies` / listDiscovered / listContacts as needed. |
| `app/api/routes/companies.py` | Add `scrape_updated_at`, `analysis_updated_at`, `contact_fetch_updated_at` to `_COMPANY_SORT_FIELDS` and `_sort_col_map` using existing subquery columns and `_ACTIVITY_EPOCH` for null safety. |
| `app/api/routes/stats.py` | Add `contact_reveal` bucket to `StatsResponse` and `_contact_reveal_stats` (join `ContactRevealJob` to `ContactRevealBatch` by `campaign_id`) so S4 can detect “started”. |
| `apps/web/src/lib/types.ts` | Add `contact_reveal?: PipelineStageStats` on `StatsResponse`. |
| `apps/web/src/components/layout/AppShell.tsx` | Optional: compact per-stage queue line from `stats` (reuse pieces from `docs/superpowers/plans/2026-04-28-pipeline-stage-status-bar.md` or inline). |
| `tests/test_companies_list.py` | New test: ordering by `scrape_updated_at` respects job timestamps. |

---

## Task 1: `contact_reveal` on `GET /v1/stats`

**Files:**

- Modify: `app/api/routes/stats.py`
- Modify: `apps/web/src/lib/types.ts`

- [ ] **Step 1:** Copy the `_contact_reveal_stats` function and `StatsResponse.contact_reveal` field from the plan in `docs/superpowers/plans/2026-04-28-pipeline-stage-status-bar.md` (Task 1 in that file). Imports: `ContactRevealBatch`, `ContactRevealJob` from `app.models.pipeline`, `ContactFetchJobState` for state enum on reveal jobs.

- [ ] **Step 2:** Add `contact_reveal?: PipelineStageStats` to `StatsResponse` in `apps/web/src/lib/types.ts` if not present.

- [ ] **Step 3:** Run:

```bash
cd /Users/avi/Documents/Projects/AI/Prospect_shortlisting && python -m compileall app/api/routes/stats.py
```

Expected: exit code 0.

- [ ] **Step 4:** Commit:

```bash
git add app/api/routes/stats.py apps/web/src/lib/types.ts
git commit -m "feat(stats): expose contact_reveal counts for S4 started signal"
```

---

## Task 2: Company list sort keys for stage MRU (S1 to S3)

**Files:**

- Modify: `app/api/routes/companies.py`
- Modify: `tests/test_companies_list.py`

- [ ] **Step 1:** Extend `_COMPANY_SORT_FIELDS`:

```python
_COMPANY_SORT_FIELDS = frozenset(
    {
        "domain",
        "created_at",
        "last_activity",
        "decision",
        "confidence",
        "scrape_status",
        "contact_count",
        "discovered_contact_count",
        "scrape_updated_at",
        "analysis_updated_at",
        "contact_fetch_updated_at",
    }
)
```

- [ ] **Step 2:** Extend `_sort_col_map` inside `list_companies` after `last_activity_expr` and subqueries exist (same function, same names `latest_scrape`, `latest_analysis`, `latest_contact_fetch`):

```python
_sort_col_map = {
    "domain": col(Company.domain),
    "created_at": col(Company.created_at),
    "last_activity": last_activity_expr,
    "decision": decision_rank,
    "confidence": latest_confidence,
    "scrape_status": latest_scrape.c.status,
    "contact_count": func.coalesce(contact_counts.c.contact_count, 0),
    "discovered_contact_count": func.coalesce(discovered_contact_counts.c.discovered_contact_count, 0),
    "scrape_updated_at": func.coalesce(latest_scrape.c.scrape_updated_at, _ACTIVITY_EPOCH),
    "analysis_updated_at": func.coalesce(latest_analysis.c.analysis_updated_at, _ACTIVITY_EPOCH),
    "contact_fetch_updated_at": func.coalesce(latest_contact_fetch.c.contact_fetch_updated_at, _ACTIVITY_EPOCH),
}
```

- [ ] **Step 3:** Add a test in `tests/test_companies_list.py` that seeds two companies, only the second has a newer `_seed_scrape_job` with newer `updated_at`, calls `list_companies(..., sort_by="scrape_updated_at", sort_dir="desc")`, and asserts domains appear in scrape-recency order.

- [ ] **Step 4:** Run:

```bash
cd /Users/avi/Documents/Projects/AI/Prospect_shortlisting && pytest tests/test_companies_list.py -v --tb=short
```

Expected: all tests pass including the new one.

- [ ] **Step 5:** Commit:

```bash
git add app/api/routes/companies.py tests/test_companies_list.py
git commit -m "feat(companies): sort by scrape, analysis, and contact-fetch activity timestamps"
```

---

## Task 3: Frontend pure module `stageViewSort.ts`

**Files:**

- Create: `apps/web/src/lib/stageViewSort.ts`

- [ ] **Step 1:** Add the following module (exactly):

```ts
import type { ActiveView } from './navigation'
import type { StatsResponse } from './types'

function stageHasWork(stats: PipelineStageStats | undefined): boolean {
  if (!stats) return false
  return (
    stats.running > 0
    || stats.queued > 0
    || stats.completed > 0
    || stats.failed > 0
    || (stats.site_unavailable ?? 0) > 0
    || (stats.stuck_count ?? 0) > 0
  )
}

/** True once that stage has seen any queue or terminal job volume (not “never touched”). */
export function isStageStartedForDefaultSort(
  view: ActiveView,
  stats: StatsResponse | null,
): boolean {
  if (!stats) return false
  switch (view) {
    case 's1-scraping':
      return stageHasWork(stats.scrape)
    case 's2-ai':
      return stageHasWork(stats.analysis)
    case 's3-contacts':
      return stageHasWork(stats.contact_fetch)
    case 's4-reveal':
      return stageHasWork(stats.contact_reveal)
    case 's5-validation':
      return stageHasWork(stats.validation)
    default:
      return false
  }
}

/** Default sort for company-based pipeline views S1 through S3. */
export function defaultCompanySortForStageView(
  view: ActiveView,
  stats: StatsResponse | null,
): { sortBy: string; sortDir: 'asc' | 'desc' } {
  const started = isStageStartedForDefaultSort(view, stats)
  if (view === 's1-scraping') {
    return started ? { sortBy: 'scrape_updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
  }
  if (view === 's2-ai') {
    return started ? { sortBy: 'analysis_updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
  }
  if (view === 's3-contacts') {
    return started ? { sortBy: 'contact_fetch_updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
  }
  return { sortBy: 'last_activity', sortDir: 'desc' }
}

/** S4 discovered list: domain first, then last_seen freshness when reveal pipeline has started. */
export function defaultDiscoveredSort(
  stats: StatsResponse | null,
): { sortBy: string; sortDir: 'asc' | 'desc' } {
  const started = isStageStartedForDefaultSort('s4-reveal', stats)
  return started ? { sortBy: 'last_seen_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
}

/** S5 uses ProspectContacts; DB-only constraint is enforced server-side. Sort: domain until validation started. */
export function defaultValidationContactSort(
  stats: StatsResponse | null,
): { sortBy: string; sortDir: 'asc' | 'desc' } {
  const started = isStageStartedForDefaultSort('s5-validation', stats)
  return started ? { sortBy: 'updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
}
```

Note: `_DISCOVERED_CONTACT_SORT_FIELDS` in `discovered_contacts.py` already includes `domain` and `last_seen_at`. `contacts.py` lists `updated_at` and `domain`.

- [ ] **Step 2:** Commit:

```bash
git add apps/web/src/lib/stageViewSort.ts
git commit -m "feat(web): stage default sort helpers (domain vs MRU)"
```

---

## Task 4: Wire `usePipelineViews` defaults and user override

**Files:**

- Modify: `apps/web/src/hooks/usePipelineViews.ts`
- Modify: `apps/web/src/App.tsx`

- [ ] **Step 0:** Add parameter **`stats: StatsResponse | null`** to **`usePipelineViews(...)`** after **`setNotice`**. Import **`StatsResponse`** from `../lib/types`. In **`App.tsx`**, pass **`stats`** where `usePipelineViews` is invoked.

- [ ] **Step 1:** Add `useRef` boolean `pipelineSortUserOverrideRef` (or separate refs per view if you prefer) default `false`.

- [ ] **Step 2:** When `onPipelineSort` (or equivalent) runs from `SortableHeader`, set **`pipelineSortUserOverrideRef.current = true`**.

- [ ] **Step 3:** When **`activeView` changes**, reset **`pipelineSortUserOverrideRef.current = false`**.

- [ ] **Step 4:** Replace the hardcoded `setPipelineSortBy('last_activity')` / `loadPipelineView(..., 'last_activity', 'desc', ...)` branch in the **`activeView` effect** (see `usePipelineViews.ts` near lines 529 to 547). After `stats` is available, defaults should come from **`defaultCompanySortForStageView(activeView, stats)`** instead of always `last_activity`. Same for the initial `void loadPipelineView(...)` call in that block: pass the computed sort pair. Add a **`useEffect`** keyed on **`stats`** that reapplies defaults when **`isStageStartedForDefaultSort`** flips from false to true (MRU mode), unless **`pipelineSortUserOverrideRef`** is true.

- [ ] **Step 5:** For **S4 reveal** (discovered contacts), wire `defaultDiscoveredSort(stats)` to **`s4RevealSortBy`** / **`s4RevealSortDir`** and `loadS4RevealView` (see `usePipelineViews.ts` around lines 216 to 244 and 407+). For **S5 validation**, the hook reuses **`s4SortBy`**, **`s4SortDir`**, and **`loadS4View`** (same file, `activeView === 's5-validation'` resets `setS4SortBy('updated_at')` today). Apply **`defaultValidationContactSort(stats)`** there instead of hardcoding `updated_at`/`desc` when the user has not overridden sort. Use separate **`s4RevealSortUserOverrideRef`** and **`s5ContactSortUserOverrideRef`** (or one ref with view checks) so column clicks still win.

- [ ] **Step 6:** Run TypeScript:

```bash
cd /Users/avi/Documents/Projects/AI/Prospect_shortlisting/apps/web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7:** Commit:

```bash
git add apps/web/src/hooks/usePipelineViews.ts
git commit -m "feat(web): apply domain vs MRU default sort per stage using stats"
```

---

## Task 5: Status shell (optional but small)

**Files:**

- Modify: `apps/web/src/components/layout/AppShell.tsx`

- [ ] **Step 1:** For each of `stats.scrape`, `analysis`, `contact_fetch`, `contact_reveal`, `validation`, if running or queued or stuck_count is positive, render one line with stage color CSS vars (`--s1` through `--s5`). If all idle, show only `as_of` time like today. Keep mobile ping using **any** stage activity.

- [ ] **Step 2:** Commit:

```bash
git add apps/web/src/components/layout/AppShell.tsx
git commit -m "feat(ui): show per-stage queue activity in AppShell header"
```

---

## Self-review

| Requirement | Task |
|-------------|------|
| Domain first, then MRU when stage starts (all five) | Tasks 3 and 4, with Task 1 for S4 signal |
| S2 AI only after scrape (`has_scrape`) | Locked; already in `pipelineQuery.ts`; Task 4 must not overwrite `stage_filter` |
| S3 fetch any company | S3 stays `stageFilter: all` in `PIPELINE_STAGE_MAP` |
| S4 reveal on fetched people | Grain is discovered list Task 4 |
| S5 validate DB emails only | `list_all_contacts` already scopes `ProspectContact` |
| Reusable observability strip | Task 5 (or extract `DesktopLiveSummary` into a tiny component file in the same PR) |

**Placeholder scan:** None. **`contact_reveal` stats block** repeats the older plan on purpose because it stays the accurate implementation sketch.

---

**Plan saved to:** `docs/superpowers/plans/2026-04-28-stage-views-sort-eligibility-status.md`

**Execution options:**

1. **Subagent-driven** — one task per worker, quick review gates.

2. **Inline** — run tasks sequentially in this session with checkpoints after Tasks 2 and 4.

Which do you want?
