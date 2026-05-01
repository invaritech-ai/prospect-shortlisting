# Pipeline stage status bar — implementation plan

> **For agentic workers:** Use subagent-driven-development or executing-plans to run tasks in order. Steps use `- [ ]` checkboxes.

**Goal:** A reusable **PipelineStageStatusBar** that shows only when *that* stage’s queue has activity, hides when idle, and lets **S1–S5** progress independently (separate active queues).

**Architecture:** Extend **`GET /v1/stats`** with a fifth `PipelineStageStats` bucket for **contact reveal** (`ContactRevealJob`), mirroring existing aggregations. The UI reads a single `StatsResponse` (already polled in `App.tsx` via `loadStats`) and renders **up to five** thin status strips—one per stage—each controlled by `running | queued | stuck_count` (same “active” rule as `DashboardView`’s `hasQueueActivity`). Visual tokens reuse existing CSS vars (`--s1` … `--s5`) from pipeline views.

**Tech stack:** FastAPI + SQLModel + Pydantic (`app/api/routes/stats.py`), React 18 + TypeScript (`apps/web`).

**Brainstorming (compressed):**

| Approach | Pros | Cons |
|----------|------|------|
| **A. Stats-only (recommended)** | One source of truth, matches workers, aligns with shell polling | Requires one backend aggregation for reveal jobs |
| B. Pure UI splitting today’s merged summary | No API change | S4 reveal never lights up correctly; violates “five separate queues” |
| C. Per-view local state only | Flexible | Duplicate logic, fights server truth |

**Decision:** Approach **A**.

---

## File map

| File | Responsibility |
|------|----------------|
| `app/api/routes/stats.py` | Add `_contact_reveal_stats()`, extend `StatsResponse`, wire `get_stats` |
| `app/models/pipeline.py` | *(no structural change)* — use `ContactRevealJob`, `ContactRevealBatch`, `Company`, `ContactFetchJobState` |
| `apps/web/src/lib/types.ts` | Add `contact_reveal?: PipelineStageStats` to `StatsResponse` |
| `apps/web/src/lib/pipelineStageStats.ts` | **New** — `PipelineStageId`, `getStageSlice(stats, stage)`, `isStageQueueActive(slice)` |
| `apps/web/src/components/pipeline/PipelineStageStatusBar.tsx` | **New** — presentational strip; `null` when inactive |
| `apps/web/src/components/pipeline/PipelineStageStatusTray.tsx` | **New** — optional wrapper: renders 1–5 bars + spacing |
| `apps/web/src/components/layout/AppShell.tsx` | Replace inlined `DesktopLiveSummary` logic with tray; extend `hasPipelineActivity` |

**Out of scope (YAGNI):** Changing `costs.totals` shape (still four buckets in `AiUsageEvent` mapping) unless product later maps usage rows to reveal; animations beyond show/hide; Vitest setup (repo has no `*.test.tsx` — verify manually).

---

## Task 1: Backend — `_contact_reveal_stats` + `StatsResponse`

**Files:**

- Modify: `app/api/routes/stats.py`

- [ ] **Step 1: Add imports** at top (after existing model imports):

```python
from app.models.pipeline import ContactRevealBatch, ContactRevealJob
```

- [ ] **Step 2: Add `_contact_reveal_stats`** immediately after `_contact_fetch_stats` (same file region ~395–436). Logic: aggregate `ContactRevealJob` joined to `ContactRevealBatch` on `campaign_id`, and `Company` for optional `upload_id` scoping. Reuse `ContactFetchJobState` for state columns and the same stuck predicate pattern as `_contact_fetch_stats` (running + `lock_expires_at` in the past).

```python
def _contact_reveal_stats(
    session: Session, campaign_id: UUID, upload_id: UUID | None = None
) -> PipelineStageStats:
    base = (
        select(
            func.count().label("total"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.SUCCEEDED, 1))).label("completed"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.FAILED, 1))).label("failed"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.RUNNING, 1))).label("running"),
            func.count(case((col(ContactRevealJob.state) == ContactFetchJobState.QUEUED, 1))).label("queued"),
            func.count(case((
                col(ContactRevealJob.terminal_state).is_(False)
                & (col(ContactRevealJob.state) == ContactFetchJobState.RUNNING)
                & col(ContactRevealJob.lock_expires_at).is_not(None)
                & (col(ContactRevealJob.lock_expires_at) < _utcnow()),
                1,
            ))).label("stuck_count"),
        )
        .select_from(ContactRevealJob)
        .join(ContactRevealBatch, col(ContactRevealJob.contact_reveal_batch_id) == col(ContactRevealBatch.id))
        .join(Company, col(Company.id) == col(ContactRevealJob.company_id))
        .where(col(ContactRevealBatch.campaign_id) == campaign_id)
    )
    if upload_id:
        base = base.where(col(Company.upload_id) == upload_id)
    row = session.exec(base).one()
    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0
    running = row.running or 0
    queued = row.queued or 0
    stuck_count = row.stuck_count or 0
    pct_done = (completed + failed) / total if total else 0.0
    return PipelineStageStats(
        total=total,
        completed=completed,
        failed=failed,
        site_unavailable=0,
        running=running,
        queued=queued,
        stuck_count=stuck_count,
        pct_done=round(pct_done * 100, 1),
        avg_job_sec=None,
        eta_seconds=None,
        eta_at=None,
    )
```

- [ ] **Step 3: Extend Pydantic `StatsResponse`** (class around lines 41–47):

```python
class StatsResponse(BaseModel):
    scrape: PipelineStageStats
    analysis: PipelineStageStats
    contact_fetch: PipelineStageStats
    contact_reveal: PipelineStageStats
    validation: PipelineStageStats
    costs: dict[str, object] | None = None
    as_of: datetime
```

- [ ] **Step 4: Wire `get_stats` return** — add keyword:

```python
        contact_reveal=_contact_reveal_stats(session, campaign_id=campaign_id, upload_id=upload_id),
```

placed after `contact_fetch=` and before `validation=`.

- [ ] **Step 5: Run Python checks**

Run from repo root:

```bash
cd /Users/avi/Documents/Projects/AI/Prospect_shortlisting && python -m compileall app/api/routes/stats.py
```

Expected: exit code 0.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes/stats.py
git commit -m "feat(stats): add contact_reveal pipeline stats for S4 reveal queue"
```

---

## Task 2: Frontend types — `StatsResponse.contact_reveal`

**Files:**

- Modify: `apps/web/src/lib/types.ts`

- [ ] **Step 1:** In `export type StatsResponse = { ... }`, insert `contact_reveal?: PipelineStageStats` after `contact_fetch` / before `validation`.

Example:

```ts
export type StatsResponse = {
  scrape: PipelineStageStats
  analysis: PipelineStageStats
  contact_fetch?: PipelineStageStats
  contact_reveal?: PipelineStageStats
  validation?: PipelineStageStats
  // ...
}
```

(Server will emit `contact_reveal` once Task 1 is deployed.)

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/types.ts
git commit -m "feat(types): add contact_reveal to StatsResponse"
```

---

## Task 3: Helpers — `pipelineStageStats.ts`

**Files:**

- Create: `apps/web/src/lib/pipelineStageStats.ts`

- [ ] **Step 1: Add module**

```ts
import type { PipelineStageStats, StatsResponse } from './types'

export type PipelineStageId = 's1' | 's2' | 's3' | 's4' | 's5'

const STAGE_META: Record<
  PipelineStageId,
  { label: string; shortLabel: string; colorVar: string; bgVar: string; statsKey: keyof StatsResponse }
> = {
  s1: { label: 'S1 · Scraping', shortLabel: 'S1', colorVar: '--s1', bgVar: '--s1-bg', statsKey: 'scrape' },
  s2: { label: 'S2 · AI Decision', shortLabel: 'S2', colorVar: '--s2', bgVar: '--s2-bg', statsKey: 'analysis' },
  s3: { label: 'S3 · Contacts', shortLabel: 'S3', colorVar: '--s3', bgVar: '--s3-bg', statsKey: 'contact_fetch' },
  s4: { label: 'S4 · Reveal', shortLabel: 'S4', colorVar: '--s4', bgVar: '--s4-bg', statsKey: 'contact_reveal' },
  s5: { label: 'S5 · Validation', shortLabel: 'S5', colorVar: '--s5', bgVar: '--s5-bg', statsKey: 'validation' },
}

export function getStageMeta(stage: PipelineStageId) {
  return STAGE_META[stage]
}

/** Returns PipelineStageStats for a stage, or undefined if key missing (pre-backend). */
export function getStageSlice(
  stats: StatsResponse | null,
  stage: PipelineStageId,
): PipelineStageStats | undefined {
  if (!stats) return undefined
  const key = STAGE_META[stage].statsKey
  const v = stats[key]
  return typeof v === 'object' && v !== null && 'running' in v ? (v as PipelineStageStats) : undefined
}

/** Active queue: matches DashboardView / AppShell “activity” semantics. */
export function isStageQueueActive(slice: PipelineStageStats | undefined): boolean {
  if (!slice) return false
  return slice.running > 0 || slice.queued > 0 || slice.stuck_count > 0
}

export function anyStageQueueActive(stats: StatsResponse | null): boolean {
  if (!stats) return false
  return (['s1', 's2', 's3', 's4', 's5'] as const).some((s) => isStageQueueActive(getStageSlice(stats, s)))
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/lib/pipelineStageStats.ts
git commit -m "feat(web): pipeline stage stats helpers for status bars"
```

---

## Task 4: Component — `PipelineStageStatusBar`

**Files:**

- Create: `apps/web/src/components/pipeline/PipelineStageStatusBar.tsx`

- [ ] **Step 1: Implement**

```tsx
import type { PipelineStageStats } from '../../lib/types'
import type { PipelineStageId } from '../../lib/pipelineStageStats'
import { getStageMeta, isStageQueueActive } from '../../lib/pipelineStageStats'

export interface PipelineStageStatusBarProps {
  stage: PipelineStageId
  slice: PipelineStageStats | undefined
  className?: string
}

/**
 * Single-stage queue status strip. Returns null when the stage has no active queue
 * or when slice is undefined.
 */
export function PipelineStageStatusBar({
  stage,
  slice,
  className = '',
}: PipelineStageStatusBarProps) {
  const meta = getStageMeta(stage)
  if (!slice || !isStageQueueActive(slice)) return null

  return (
    <div
      className={`flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md border border-(--oc-border) px-2 py-1 text-xs ${className}`.trim()}
      style={{ background: `var(${meta.bgVar})` }}
      role="status"
      aria-label={`${meta.label} queue`}
    >
      <span className="shrink-0 font-bold" style={{ color: `var(${meta.colorVar})` }}>
        {meta.shortLabel}
      </span>
      <span className="min-w-0 truncate text-(--oc-text)">
        {slice.running} running · {slice.queued} queued
        {slice.stuck_count > 0 ? ` · ${slice.stuck_count} stuck` : ''}
      </span>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/pipeline/PipelineStageStatusBar.tsx
git commit -m "feat(ui): add PipelineStageStatusBar presentational component"
```

---

## Task 5: Tray — optional layout wrapper

**Files:**

- Create: `apps/web/src/components/pipeline/PipelineStageStatusTray.tsx`

- [ ] **Step 1:**

```tsx
import type { StatsResponse } from '../../lib/types'
import type { PipelineStageId } from '../../lib/pipelineStageStats'
import { getStageSlice } from '../../lib/pipelineStageStats'
import { PipelineStageStatusBar } from './PipelineStageStatusBar'

const STAGES: PipelineStageId[] = ['s1', 's2', 's3', 's4', 's5']

export interface PipelineStageStatusTrayProps {
  stats: StatsResponse | null
  className?: string
}

/** Renders zero or more stage bars (only active stages). When stats is null, renders nothing — parent shows a single loading line. */
export function PipelineStageStatusTray({
  stats,
  className = '',
}: PipelineStageStatusTrayProps) {
  if (!stats) return null
  return (
    <div className={`flex min-w-0 flex-col gap-1 ${className}`.trim()}>
      {STAGES.map((stage) => (
        <PipelineStageStatusBar
          key={stage}
          stage={stage}
          slice={getStageSlice(stats, stage)}
        />
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/pipeline/PipelineStageStatusTray.tsx
git commit -m "feat(ui): add PipelineStageStatusTray layout wrapper"
```

---

## Task 6: Integrate — `AppShell.tsx`

**Files:**

- Modify: `apps/web/src/components/layout/AppShell.tsx`

- [ ] **Step 1: Imports**

Add:

```ts
import { anyStageQueueActive } from '../../lib/pipelineStageStats'
import { PipelineStageStatusTray } from '../pipeline/PipelineStageStatusTray'
```

- [ ] **Step 2: Replace `hasPipelineActivity`**

Either delete `hasPipelineActivity` and inline `stats && anyStageQueueActive(stats)`, or redefine:

```ts
function hasPipelineActivity(stats: StatsResponse | null) {
  return stats !== null && anyStageQueueActive(stats)
}
```

- [ ] **Step 3: Remove `DesktopLiveSummary`** function component (lines 39–65) entirely.

- [ ] **Step 4: Desktop header slot** — replace the `<DesktopLiveSummary stats={stats} />` block with the same **`stats === null` branch as today** (single muted “Loading activity…”), then the tray:

```tsx
{!stats ? (
  <span className="truncate text-xs text-(--oc-muted)">Loading activity…</span>
) : (
  <PipelineStageStatusTray stats={stats} className="max-h-[4.5rem] overflow-y-auto" />
)}
```

Adjust `max-h` if five stacked rows overflow awkwardly on small widths; alternatively use `flex flex-row flex-wrap gap-1` inside the tray (small follow-up).

- [ ] **Step 5: Mobile ping dot** — `activity` already uses `hasPipelineActivity`; no change beyond Step 2 if `hasPipelineActivity` uses `anyStageQueueActive`.

- [ ] **Step 6: Typecheck**

```bash
cd /Users/avi/Documents/Projects/AI/Prospect_shortlisting/apps/web && npx tsc --noEmit
```

Expected: no errors referencing `StatsResponse` or new components.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/layout/AppShell.tsx
git commit -m "feat(ui): use PipelineStageStatusTray in AppShell for per-stage queues"
```

---

## Task 7: Call-site parity — `DashboardView.tsx` (optional but recommended)

**Files:**

- Modify: `apps/web/src/components/views/pipeline/DashboardView.tsx`

- [ ] **Step 1:** Replace the inline `hasQueueActivity` computation (lines ~131–136) with `anyStageQueueActive(stats)` imported from `lib/pipelineStageStats` so **one definition** drives both shell and dashboard.

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/views/pipeline/DashboardView.tsx
git commit -m "refactor(ui): unify queue activity check with pipelineStageStats"
```

---

## Manual verification

1. Start API + web; select a campaign with an empty queue — **no** stacked bars once `stats` loads (only the “Loading activity…” single line while `stats` is null).
2. Enqueue S1 scrape jobs — **only** S1 bar appears with running/queued copy.
3. Run S4 email reveal — **only** S4 appears once `contact_reveal` stats propagate (needs Task 1 deployed).
4. Run S5 validation — S5 strip independent of others.
5. Resize desktop header: tray scrolls (`overflow-y-auto`) before overlapping logout.

---

## Self-review

| Requirement | Task |
|-------------|------|
| Reusable component | Task 4 + optional Task 5 |
| Visible when queue active | `isStageQueueActive` / `PipelineStageStatusBar` return null otherwise |
| Hides when no task | same |
| S1–S5 tracked separately | `getStageSlice` keys + Task 1 reveal stats |
| Gaps addressed | Backend reveal aggregation was mandatory for correct S4; cost totals unchanged (documented out of scope) |

**Placeholder scan:** None —_STATS functions and TS helpers are concrete.

---

**Plan complete.** Saved to `docs/superpowers/plans/2026-04-28-pipeline-stage-status-bar.md`.

**Execution:** use **subagent-driven-development** (one task per subagent + review) or **executing-plans** (batch in-session). Which do you prefer?
