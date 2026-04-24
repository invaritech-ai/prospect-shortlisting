# Backend-Driven Filters Fix

**Date:** 2026-04-24
**Branch:** feat/s3-s4-s5-backend-realign

## Problem

S4RevealView (newly built) and S5ValidationView (formerly S4) do not follow the established backend-driven filter pattern used by S1–S3. Specific failures:

- **Pattern A — missing reload trigger**: `onS4MatchFilterChange` and `onS4RevealPagePrev/Next` update state but never call `loadS4RevealView()`. Changing filters shows stale data.
- **Pattern A — no stale-request cancellation**: `loadS4RevealView` has no request ref counter, so rapid filter clicks can overwrite newer responses with stale ones.
- **Pattern B — missing disabled states**: Filter chips, checkboxes, Pager, LetterStrip, and SortableHeader columns in S4RevealView and S5ValidationView are all interactive during loading, allowing stacked requests.
- **Missing backend param**: `listDiscoveredContacts` only supports `matched_only=true` (filter to matched) or nothing (all). No way to fetch unmatched-only contacts.

S1, S2, S3 are correct and serve as the reference pattern.

---

## Design

### Task 1: Backend — replace `matched_only` with `title_match`

**File:** `app/api/routes/contacts.py` (or discovered contacts route)

Replace the `matched_only: bool = Query(default=False)` parameter with:
```python
title_match: Optional[bool] = Query(default=None)
```

Semantics:
- `title_match=null` (omitted) → all contacts
- `title_match=true` → matched only
- `title_match=false` → unmatched only

Update `_apply_discovered_filters`:
```python
if title_match is not None:
    stmt = stmt.where(col(DiscoveredContact.title_match) == title_match)
```

Remove the old `matched_only` branch entirely.

**File:** `apps/web/src/lib/api.ts`

In `listDiscoveredContacts`, rename `matchedOnly?: boolean` → `titleMatch?: boolean` and update the query param from `matched_only` → `title_match`.

---

### Task 2: Fix S4RevealView — stale cancellation, reload wiring, disabled states

**File:** `apps/web/src/hooks/usePipelineViews.ts`

**Stale-request cancellation** (mirror S1–S3 pattern):
```ts
const s4RevealRequestRef = useRef(0)
const s4RevealForegroundRequestRef = useRef(0)
```

`loadS4RevealView` increments `s4RevealRequestRef` on each call, stores the id, checks `s4RevealRequestRef.current !== requestId` before any `setState`, and only clears `isS4RevealLoading` if `s4RevealForegroundRequestRef.current === requestId`.

**Two separate effects:**

1. **View-change effect** (already exists, update it): on `activeView === 's4-reveal'` — reset `s4MatchFilter → 'all'`, `s4RevealOffset → 0`, clear selection, call `loadS4RevealView()`.

2. **Filter/offset effect** (new): watches `s4MatchFilter` and `s4RevealOffset` while on `s4-reveal`:
```ts
useEffect(() => {
  if (activeView !== 's4-reveal' || !selectedCampaignId) return
  void loadS4RevealView()
}, [activeView, selectedCampaignId, s4MatchFilter, s4RevealOffset, loadS4RevealView])
```
`loadS4RevealView` must be excluded from the view-change effect's deps (or the view-change effect must not include `loadS4RevealView` — use a stable callback pattern or separate the concerns clearly to avoid the view-change effect firing on every filter change).

**`listDiscoveredContacts` call** uses `titleMatch`:
```ts
titleMatch: s4MatchFilter === 'matched' ? true
          : s4MatchFilter === 'unmatched' ? false
          : undefined
```

**File:** `apps/web/src/components/views/pipeline/S4RevealView.tsx`

- Filter chips → `disabled={isLoading}`
- Select-all checkbox → `disabled={isLoading || isRevealing}`
- Row checkboxes → `disabled={isLoading || isRevealing}`
- `<Pager ... disabled={isLoading} />`
- `<SelectionBar ... disabled={isLoading || isRevealing} />`

---

### Task 3: Fix S5ValidationView — disabled states

**File:** `apps/web/src/components/views/pipeline/S4ValidationView.tsx`

No hook changes needed — backend wiring already works. Add `disabled` props only:

| Control | Disabled condition |
|---|---|
| `LetterStrip` | `isLoading \|\| isValidating` |
| 8 verification filter chips | `isLoading` |
| `Pager` | `isLoading` |
| 7 `SortableHeader` columns | `isLoading` |
| Select-all checkbox | `isLoading \|\| isValidating` |
| Row checkboxes | `isLoading \|\| isValidating` |

`isLoading` and `isValidating` are already in the props interface.

---

### Task 4: TitleRulesPanel — seed button

**File:** `apps/web/src/components/panels/TitleRulesPanel.tsx`

Add `disabled={isLoading || isAdding}` to the "Seed default rules" button. Both state vars already exist.

---

## Reference pattern (S1–S3)

```ts
// Stale cancellation
const xRequestRef = useRef(0)
const xForegroundRequestRef = useRef(0)

const loadXView = useCallback(async (...params) => {
  const requestId = xRequestRef.current + 1
  xRequestRef.current = requestId
  xForegroundRequestRef.current = requestId
  setIsXLoading(true)
  try {
    const data = await fetchX(params)
    if (xRequestRef.current !== requestId) return  // stale, discard
    setXData(data)
  } catch (err) {
    if (xRequestRef.current !== requestId) return
    setError(parseApiError(err))
  } finally {
    if (xForegroundRequestRef.current === requestId) setIsXLoading(false)
  }
}, [deps])

// View-change effect — resets state
useEffect(() => {
  if (activeView === 'x-view') {
    resetXState()
    void loadXView(defaultParams)
  }
}, [activeView, ...])

// Filter/offset effect — reloads on change
useEffect(() => {
  if (activeView !== 'x-view' || !selectedCampaignId) return
  void loadXView(currentParams)
}, [activeView, selectedCampaignId, xFilter, xOffset, loadXView])
```

All interactive controls: `disabled={isXLoading}`.

---

## Test plan

1. `cd apps/web && npx tsc --noEmit` — zero errors after all tasks
2. S4 Reveal: change filter chip while loading → button is non-interactive; rapid clicks produce only one final result
3. S4 Reveal: "Unmatched" filter returns only contacts with `title_match=false`
4. S4 Reveal: page prev/next triggers new API call with updated offset
5. S5 Validation: all filter chips, Pager, letter strip non-interactive during loading
6. TitleRulesPanel: seed button greyed during load or add
