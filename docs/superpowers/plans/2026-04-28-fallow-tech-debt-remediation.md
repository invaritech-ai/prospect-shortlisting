# Fallow tech-debt remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce Fallow noise and real dead surface area in `apps/web` without destabilizing production behavior: eliminate orphaned views and unused exports, optionally trim duplication and complexity in a second phase.

**Architecture:** Treat the work as three layers: (1) **truth** — confirm what is unreachable vs false positives; (2) **delete or wire** — remove dead files and exports, or connect them if product still needs them; (3) **incremental refactors** — duplication and large functions only after baseline is green and scoped.

**Tech Stack:** React (Vite), TypeScript, existing `npx fallow` workflow in `apps/web`.

---

## Brainstorming summary

### What the report is telling you

| Bucket | Count | Interpretation |
|--------|------:|----------------|
| Unused files | 7 | Matches current `App.tsx`: legacy views and `App.css` / `BulkActionBar` are not imported from any entry. |
| Unused exports | 19 + 21 types | Symbols exported for reuse that nothing imports; safe to drop or make module-private unless part of a deliberate public API. |
| Unused `autoprefixer` | 1 | Likely PostCSS consumes it indirectly; verify PostCSS config before removing. |
| Duplication | 49 groups | Largest ROI families: `PromptLibraryPanel` ↔ `ScrapePromptLibraryPanel`, pipeline stage views, chunks of `api.ts`. |
| Complexity | 152 “above threshold” | Symptoms of large components (`App`, `usePipelineViews`, pipeline views). Not all need fixing at once. |

### Success criteria (pick what you enforce in CI)

- **Minimum:** `npx fallow` passes **dead-code** gates you care about (often: zero unused files, or suppressed with documented reason).
- **Stretch:** Duplication and complexity sections improved incrementally; no requirement to hit zero on first pass.

### Three approaches

| Approach | Pros | Cons |
|----------|------|------|
| **A. Delete-first** | Fastest; aligns with Fallow “start with telemetry.ts”; shrinks bundle and confusion | Needs quick product confirm that legacy views are not coming back on short horizon |
| **B. Archive branch + delete** | Psychological safety; easy rollback | Extra git ceremony |
| **C. Re-wire legacy views** | Keeps old UIs reachable (e.g. `/companies`) | Ongoing maintenance; fights current app shell unless fully integrated |

**Recommendation:** **A**, with a tagged release or branch snapshot **B** if anyone relies on those screens for demos. **C** only if PM explicitly wants old list views back.

### Risks and mitigations

- **False positive on `autoprefixer`:** Read `postcss.config.*` / `vite.config.*`; if referenced by string only, Fallow may flag it—keep dep or document in `package.json` comment / fallow config if supported.
- **`api.ts` unused functions:** May be intended for future endpoints; prefer `export` → file-private or delete after grep confirms no dynamic usage.
- **Deleting views:** Run `pnpm test` / `pnpm build` and smoke-test navigation after removal.

---

## File map (apps/web)

| Area | Files |
|------|--------|
| Entry | `src/main.tsx` → `src/App.tsx` |
| Reported dead | `src/App.css`, `src/components/ui/BulkActionBar.tsx`, `src/components/views/{Companies,Contacts,AnalysisRuns,AnalyticsSnapshot,ScrapeJobs}View.tsx` |
| Dead exports hot spots | `src/lib/telemetry.ts`, `src/lib/navigation.ts`, `src/lib/api.ts`, `src/lib/types.ts`, hooks under `src/hooks/` |
| Duplication hotspots | `PromptLibraryPanel.tsx`, `ScrapePromptLibraryPanel.tsx`, `S1ScrapingView.tsx`, `S2AIDecisionView.tsx`, `src/lib/api.ts` |
| Complexity hotspots | `src/App.tsx`, `src/hooks/usePipelineViews.ts`, pipeline `*View.tsx` files |

---

## Phase 0 — Baseline and guardrails

### Task 0.1: Lock baseline

**Files:** None (commands only)

- [ ] From `apps/web`, run `npx fallow` and save output (or append to this doc) for before/after.
- [ ] Run `pnpm build` and `pnpm test` (or repo-standard equivalents) and ensure green before edits.

### Task 0.2: Product decision on legacy views

**Files:** Team communication / ticket

- [ ] Confirm with owner: **delete** the seven unused files vs **restore routing** in `App.tsx`/navigation. Plan below assumes **delete**.

---

## Phase 1 — Dead files and obvious dependency cleanup

### Task 1.1: Remove orphaned view files and CSS

**Files:**

- Delete: `apps/web/src/App.css` (if unused — verify no `@import`/`import` of it)
- Delete: `apps/web/src/components/ui/BulkActionBar.tsx`
- Delete: `apps/web/src/components/views/CompaniesView.tsx`
- Delete: `apps/web/src/components/views/ContactsView.tsx`
- Delete: `apps/web/src/components/views/AnalysisRunsView.tsx`
- Delete: `apps/web/src/components/views/AnalyticsSnapshotView.tsx`
- Delete: `apps/web/src/components/views/ScrapeJobsView.tsx`

- [ ] Grep the repo for imports of each filename; remove any re-exports or test-only references.
- [ ] If `AnalysisDetailPanel` or other panels imported only from deleted views, either delete those panels or move shared pieces—run TypeScript and fix errors.
- [ ] `pnpm build` — expect TS errors listing any broken imports; fix until clean.

### Task 1.2: `autoprefixer`

**Files:** `package.json`, `postcss.config.*`, `vite.config.*`

- [ ] Confirm whether PostCSS plugin list references `autoprefixer`. If Vite/PostCSS pulls it in implicitly, you may still need the package; if truly unused, remove from `devDependencies`.
- [ ] Re-run build; fix CSS pipeline if anything breaks.

---

## Phase 2 — Unused exports and types (Fallow “quick wins”)

Order matches Fallow’s refactoring target list: start with **telemetry**, then **navigation**, then **api/types**, then small UI/hook exports.

### Task 2.1: `src/lib/telemetry.ts`

**Files:** `apps/web/src/lib/telemetry.ts`

- [ ] Remove or make file-private: `scrapeStatus`, `runStatus`, `buildAnalyticsSnapshot`, `topScrapeErrorCodes`, `topFailedRunPrompts` if nothing imports them after Phase 1.
- [ ] If entire file becomes empty or trivial, delete the file and strip imports.

### Task 2.2: `src/lib/navigation.ts`

**Files:** `apps/web/src/lib/navigation.ts`

- [ ] Remove `DEFAULT_ACTIVE_VIEW` and `isActiveView` if unused, or use them in `App.tsx` if that was the intent—do not leave orphan exports.

### Task 2.3: `src/lib/api.ts` and `src/lib/types.ts`

**Files:** `apps/web/src/lib/api.ts`, `apps/web/src/lib/types.ts`

- [ ] Run `npx fallow --format json` and list each unused export/type; for each symbol, either delete or convert to non-exported `type` / function.
- [ ] Pay attention to types that might be used only in tests — either export from a `*.test.ts`-local helper or keep one re-export in a test utilities file (only if needed).

### Task 2.4: Small exports (`badgeUtils`, `icons`, hooks)

**Files:** `apps/web/src/components/ui/badgeUtils.ts`, `apps/web/src/components/ui/icons.tsx`, `apps/web/src/hooks/usePipelineViews.ts`, other files listed in report

- [ ] `decisionVariant` — delete or inline.
- [ ] `IconFilter` — delete export if unused or use where intended.
- [ ] `DEFAULT_PAGE_SIZE` — keep internal const without export if only used inside the hook file.

### Task 2.5: Confirm dead-code section clean

**Files:** none

- [ ] Run `npx fallow` — aim for zero **unused files** and minimal **unused exports/types**, or intentional `// fallow-ignore-next-line` with one-line rationale for anything that must stay exported (e.g. codegen).

---

## Phase 3 — Duplication (optional, multi-PR)

**Principle:** Extract shared building blocks only where two files must stay in sync; avoid abstracting one-off similarity.

### Task 3.1: Prompt library panels

**Files:** `PromptLibraryPanel.tsx`, `ScrapePromptLibraryPanel.tsx`, new shared module under `apps/web/src/components/panels/shared/` or similar

- [ ] Extract the largest clone groups (table rows, empty states, save flows) into parameterized components or hooks.
- [ ] Keep behavior identical; add a quick smoke test or Storybook story if the project uses them.

### Task 3.2: Pipeline stage views (S1/S2/S3)

**Files:** `S1ScrapingView.tsx`, `S2AIDecisionView.tsx`, `S3ContactFetchView.tsx`, `FullPipelineView.tsx`

- [ ] Extract shared “stage header / bulk bar / status chip” patterns into `components/views/pipeline/shared/`.
- [ ] Limit scope to 1–2 extractions per PR to keep review small.

### Task 3.3: `api.ts` duplication

**Files:** `apps/web/src/lib/api.ts`

- [ ] Identify repeated `request(...)` patterns; introduce small helpers `getJson`, `deleteJson`, etc., only if multiple call sites match exactly.

---

## Phase 4 — Complexity (optional, ongoing)

Not a single sprint; track in backlog.

| Target | Suggested move |
|--------|------------------|
| `usePipelineViews` (1535 LOC) | Split by stage: `useS1View`, `useS4Reveal`, full-pipeline, etc., or by concern: fetch vs selection vs mutations |
| `App` (1246 LOC) | Extract providers, campaign bootstrap, and view switch into `AppLayout.tsx` / hooks |
| CRITICAL pipeline views | Extract presentational subcomponents; keep data in hooks |

- [ ] Add one refactoring task per sprint; measure with `npx fallow` complexity section trending down.

---

## Verification checklist

After each phase:

```bash
cd apps/web && pnpm exec tsc --noEmit && pnpm build && pnpm test && npx fallow
```

- [ ] Phase 1: Build + tests green; dead **files** count zero.
- [ ] Phase 2: Fallow unused exports/types acceptable; no unintended runtime behavior change.
- [ ] Phase 3–4: Optional; each PR independently reviewable.

---

## Self-review (writing-plans)

1. **Spec coverage:** Addresses dead files, deps, unused exports/types, duplication, complexity, verification — matches terminal report.
2. **Placeholders:** No TBD tasks; deliberate “confirm with owner” only where product decision is required.
3. **Consistency:** Paths scoped to `apps/web` as in Fallow cwd.

---

## Execution handoff

**Plan saved to:** `docs/superpowers/plans/2026-04-28-fallow-tech-debt-remediation.md`.

**Execution options:**

1. **Subagent-driven** — One task per checkbox batch, review between tasks (recommended for Phase 3+).
2. **Inline** — Phases 0–2 in one session with frequent `build`/`fallow` checks.

Which approach do you want for implementation?
