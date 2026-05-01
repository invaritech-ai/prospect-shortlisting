# App shell decomposition — brainstorming-backed implementation plan

> **Context:** `apps/web` has **`App.tsx` ~1.3k LOC** and **`usePipelineViews.ts` ~1.8k LOC**. **`telemetry.ts`** reports ~**83% dead exports** in Fallow — understandable discomfort “walking hotspot.”  
> **Audience:** Engineers refactoring incrementally without freezing features.

---

## 1. Brainstorming — goals and constraints

### Goals

| Goal | Measurable signal |
|------|-------------------|
| **Smaller units of change** | No single file holds “whole product”; typical PR touches &lt;400 LOC in one place. |
| **Testable seams** | Hooks and pure modules have clear inputs/outputs; fewer “god” props. |
| **Telemetry honest** | Either **one exported entry** (`buildOperationsEvents`) or documented public API — not 5 unused exports. |
| **No behavior drift** | Split is **move code** first; behavior changes are separate PRs. |

### Constraints

- **Incremental delivery:** ship vertical slices (e.g. “extract full-pipeline state”) with `pnpm build` green after each merge.
- **Match existing patterns:** same `api`/`types` imports, same error handling (`parseApiError`, toasts).
- **React 19 / current stack:** no new state library unless you explicitly want one later.

---

## 2. Approaches (trade-offs)

### A. “Strangler” file split (recommended)

**What:** Move cohesive blocks into new files (`*.ts` / `*.tsx`) wired by imports; **keep** a thin `App.tsx` and thin `usePipelineViews.ts` as facades until fully hollowed out.

| Pros | Cons |
|------|------|
| Lowest risk, easy review | Temporary “re-export” noise |
| Aligns with Git history (moves vs rewrites) | Naming discipline needed |

### B. Hooks explosion first

**What:** Immediately split `usePipelineViews` into `useFullPipeline`, `useStageCompanies`, `useS4Contacts`, … then compose.

| Pros | Very clear boundaries | Cons | Many new files + plumbing churn up front; composition bugs if interfaces wrong |

### C. Big-bang rewrite

**What:** Redesign state machine / context providers for the whole app.

| Pros | Clean architecture possible | Cons | **Highest** regression risk; **reject** for this effort unless product asks for a redesign |

**Recommendation:** **A**, with **selected B** inside the hook: introduce **2–4 child hooks** where boundaries are already obvious (full pipeline vs stage views vs S4 slices), not ten micro-hooks on day one.

---

## 3. Discovery — what the codebase already tells us

### `telemetry.ts`

- **`buildOperationsEvents`** is imported by `App.tsx` — **keep and export**.
- **`scrapeStatus` / `runStatus`** are **only** used inside telemetry for building events and for **unused** `buildAnalyticsSnapshot` / `top*` helpers — **drop `export`** or inline; **delete** `buildAnalyticsSnapshot`, `topScrapeErrorCodes`, `topFailedRunPrompts`, and `CountBucket` export if nothing imports them.
- After cleanup, Fallow “83% dead” should collapse to a **small**, purpose-built module (~60–80 LOC).

### `App.tsx` (~1.3k LOC)

From structure: **auth**, **route/view state**, **polling** (`pollFailuresRef`), **campaign + uploads**, **stats/costs**, **operations event list** (`buildOperationsEvents`), **panel wiring**, **view switch** (`activeView`), **Toast**, **pipeline hook** props drilling.

Natural seams:

1. **`useAppBootstrapAuth`** — auth boot, `getCurrentUser`, login/logout, `AUTH_REQUIRED`.
2. **`useCampaignWorkspace`** (or split further) — selected campaign, uploads, costs, stats refresh, URL ↔ state.
3. **`useOperationsFeed`** — recent scrape jobs/runs → `buildOperationsEvents`, merge order, polling side effects.
4. **`AppAuthenticatedContent` **— presentational: `AppShell` + view switch + panels; **props** from hooks above.

Even **two** extractions (bootstrap + “main body” component) cuts `App.tsx` sharply.

### `usePipelineViews.ts` (~1.8k LOC)

Large **single hook** with disjoint concerns in one return object:

- Full pipeline list + actions  
- S1–S3 shared pipeline company list + sorting + selection + bulk actions  
- S4 contacts / validation / reveal branches (long `UsePipelineViewsResult` interface)

**Split strategy:**

1. **Phase 1 — types out:** move `UsePipelineViewsResult` + related types to `usePipelineViews.types.ts` (or colocated `types.ts`). Reduces noise; no runtime change.
2. **Phase 2 — extract loaders:** pure async helpers or `*_loadCompanies` functions in `lib/pipelineLoaders.ts` **if** duplication between `loadPipelineView` / `loadFullPipelineView` warrants it (Fallow already hinted clone groups inside the hook).
3. **Phase 3 — slice hooks:**
   - `useFullPipelineList` — state + handlers only for full-pipeline screen  
   - `useStagePipelineList` — S1–S3 shared slice  
   - `useS4PipelineSlice` — S4 validation/contacts/reveal (as far as coupling allows)  

   Compose in `usePipelineViews` delegating to these, **same public API** for `App.tsx` initially (so App diff is minimal).

4. **Phase 4** — optionally **narrow `App.tsx` props**: pass one context or grouped props objects (`pipeline={...}` / `fullPipeline={...}`) to reduce prop count.

---

## 4. Phased implementation checklist

### Phase T — Telemetry (same day, trivial)

- [ ] Remove unused exports (`buildAnalyticsSnapshot`, `topScrapeErrorCodes`, `topFailedRunPrompts`); delete dead helpers (`percent`, `topCounts`) if orphaned.
- [ ] Make `scrapeStatus` / `runStatus` **non-exported**.
- [ ] `pnpm exec tsc --noEmit` + `pnpm build` in `apps/web`.

### Phase A — `App.tsx` carve-out (1–2 PRs)

- [ ] Extract **`useAuthSession`** / **`useAppAuth`**: bootstrap, login handler, guards.
- [ ] Extract **`AppRoutesOrShell`** component: everything after auth ready — **or** at minimum **`AuthenticatedApp`** with current body.
- [ ] Leave polling + `buildOperationsEvents` either in **`useRecentActivity`** (new hook) or a small **`operationsTimeline.ts`** module.

### Phase B — `usePipelineViews` decomposition (several PRs)

- [ ] **`usePipelineViews.types.ts`**: interface + exported constants consumed by App only (`PAGE_SIZE_OPTIONS` etc.).
- [ ] Identify **duplicate blocks** in hook (sort reset, pagination, select-all) → internal functions in `pipelineViewActions.ts`.
- [ ] **`useFullPipelineViewState`** + **`useStagePipelineViewState`** (names flexible) — **internal** composition first; keep `usePipelineViews` as the public export until stable.
- [ ] Add **focused tests** for pure helpers (sort mapping, ID list dedupe) where risk is highest — optional but aligns with `stageViewSort` Fallow note.

### Phase C — Hardening

- [ ] Run `npx fallow` — expect **telemetry** off the “refactor targets” top list; complexity may still flag large views until further UI splits.
- [ ] Document in **README or CLAUDE.md** (only if you want): “App composition: `App.tsx` → hooks in `hooks/` …”

---

## 5. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Subtle re-render or stale closure after hook split | Move **one slice** per PR; manual smoke: campaign switch, S1→S4 navigation, bulk select. |
| Circular imports | New modules depend **down** toward `lib/`; hooks avoid importing `App.tsx`. |
| Scope creep | **No** new product features in decomposition PRs. |

---

## 6. Success criteria (exit)

- **`telemetry.ts`**: single clear purpose; Fallow dead-export noise minimal for that file.
- **`App.tsx`**: **&lt; 600 LOC** as a stretch goal post-extraction — or documented sections with **≤200 LOC** per extracted module.
- **`usePipelineViews.ts`**: either **&lt; 800 LOC** + satellite files **or** split into **named hooks** each **&lt; 500 LOC** with a thin composer.

---

## 7. Self-review vs brainstorming checklist

| Brainstorm item | Covered |
|-----------------|--------|
| Project context | Yes — actual file roles and telemetry grep |
| Multiple approaches | A / B / C with recommendation |
| Design sections | Goals, seams, phases, risks |
| **Not** implementation code | Plan only |

---

## 8. Execution handoff

When you’re ready to implement: use **task-by-task** execution (subagent or inline), **one phase per branch** preferred.

**Suggested first merge:** Phase T (telemetry slimming) — **low risk**, immediate Fallow morale boost.
