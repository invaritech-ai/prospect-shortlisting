# Backend-Driven Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all filter/sort/pagination controls across S4RevealView, S5ValidationView, and TitleRulesPanel to be fully backend-driven with stale-request cancellation and UI blocking during loads.

**Architecture:** Four sequential tasks — backend contract first (adds `title_match` param replacing `matched_only`), then S4RevealView wiring (stale cancellation + separate filter-change effect + disabled states), then S5ValidationView disabled states, then TitleRulesPanel seed button. Each task is independently compilable.

**Tech Stack:** FastAPI (Python), SQLModel, React 18, TypeScript, custom `usePipelineViews` hook

---

## File Map

| File | Change |
|---|---|
| `app/api/routes/discovered_contacts.py` | Replace `matched_only` with `title_match: bool \| None` everywhere |
| `apps/web/src/lib/api.ts` | Rename `matchedOnly` → `titleMatch` in `listDiscoveredContacts` and `listCompanyDiscoveredContacts` |
| `apps/web/src/hooks/usePipelineViews.ts` | Add stale-cancellation refs, rewrite `loadS4RevealView`, add filter-change effect, fix view-change effect |
| `apps/web/src/components/views/pipeline/S4RevealView.tsx` | Add `disabled` to filter chips, checkboxes, Pager, SelectionBar |
| `apps/web/src/components/views/pipeline/S4ValidationView.tsx` | Add `disabled` to LetterStrip, filter buttons, Pager, SortableHeaders, checkboxes |
| `apps/web/src/components/panels/TitleRulesPanel.tsx` | Add `disabled` to seed button |

---

## Task 1: Replace `matched_only` with `title_match` in backend and API client

### Files
- Modify: `app/api/routes/discovered_contacts.py`
- Modify: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Update `_apply_discovered_filters` helper**

In `app/api/routes/discovered_contacts.py`, the function signature at line 72 currently has `matched_only: bool = False`. Replace the entire function signature and filter branch:

```python
def _apply_discovered_filters(
    stmt,
    *,
    title_match: bool | None = None,
    provider: str | None = None,
    search: str | None = None,
    company_id: UUID | None = None,
    company_ids: list[UUID] | None = None,
    letters: list[str] | None = None,
):
    stmt = stmt.where(col(DiscoveredContact.is_active).is_(True))
    if title_match is not None:
        stmt = stmt.where(col(DiscoveredContact.title_match) == title_match)
    if provider:
        stmt = stmt.where(col(DiscoveredContact.provider) == provider.strip().lower())
    if company_id is not None:
        stmt = stmt.where(col(DiscoveredContact.company_id) == company_id)
    if company_ids:
        stmt = stmt.where(col(DiscoveredContact.company_id).in_(company_ids))
    if letters:
        stmt = stmt.where(_domain_first_letter_expr().in_(letters))
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(DiscoveredContact.first_name).like(term),
                func.lower(DiscoveredContact.last_name).like(term),
                func.lower(DiscoveredContact.title).like(term),
                func.lower(Company.domain).like(term),
            )
        )
    return stmt
```

- [ ] **Step 2: Update `list_discovered_contacts` route**

At line 107, replace the route signature and both `_apply_discovered_filters` calls:

```python
@router.get("/discovered-contacts", response_model=DiscoveredContactListResponse)
def list_discovered_contacts(
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    provider: str | None = Query(default=None),
    company_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    letters: str | None = Query(default=None),
    count_by_letters: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> DiscoveredContactListResponse:
```

Update the first `_apply_discovered_filters` call (around line 125):
```python
    stmt = _apply_discovered_filters(
        stmt,
        title_match=title_match,
        provider=provider,
        search=search,
        company_id=company_id,
        letters=letter_values or None,
    )
```

Update the second `_apply_discovered_filters` call in the `count_by_letters` block (around line 166):
```python
        letter_stmt = _apply_discovered_filters(
            letter_stmt,
            title_match=title_match,
            provider=provider,
            search=search,
            company_id=company_id,
        )
```

- [ ] **Step 3: Update `list_company_discovered_contacts` route**

At line 189, replace `matched_only` everywhere in this route:

```python
@router.get("/companies/{company_id}/discovered-contacts", response_model=DiscoveredContactListResponse)
def list_company_discovered_contacts(
    company_id: UUID,
    campaign_id: UUID = Query(...),
    title_match: bool | None = Query(default=None),
    provider: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> DiscoveredContactListResponse:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return list_discovered_contacts(
        campaign_id=campaign_id,
        title_match=title_match,
        provider=provider,
        company_id=company_id,
        search=search,
        limit=limit,
        offset=offset,
        letters=None,
        count_by_letters=False,
        session=session,
    )
```

- [ ] **Step 4: Update `list_discovered_companies` route**

At line 252, this route also uses `matched_only`. Replace:

```python
@router.get("/discovered-contacts/companies", response_model=ContactCompanyListResponse)
def list_discovered_companies(
    campaign_id: UUID = Query(...),
    search: str | None = Query(default=None),
    title_match: bool | None = Query(default=None),
    match_gap_filter: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ContactCompanyListResponse:
```

And replace the filter branch around line 318 (was `if matched_only:`):
```python
    if title_match is not None:
        stmt = stmt.where(col(DiscoveredContact.title_match) == title_match)
```

- [ ] **Step 5: Update frontend `listDiscoveredContacts` in api.ts**

Find `listDiscoveredContacts` (line ~594). Replace the `matchedOnly` option and param:

```typescript
export async function listDiscoveredContacts(
  options: {
    campaignId: string
    titleMatch?: boolean
    provider?: string
    companyId?: string
    search?: string
    limit?: number
    offset?: number
    letters?: string[]
    countByLetters?: boolean
  },
): Promise<DiscoveredContactListResponse> {
  const params = new URLSearchParams()
  params.set('campaign_id', options.campaignId)
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.provider) params.set('provider', options.provider)
  if (options.companyId) params.set('company_id', options.companyId)
  if (options.search) params.set('search', options.search)
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  if (options.letters && options.letters.length > 0) params.set('letters', options.letters.join(','))
  if (options.countByLetters) params.set('count_by_letters', 'true')
  return request<DiscoveredContactListResponse>(`/v1/discovered-contacts?${params.toString()}`)
}
```

- [ ] **Step 6: Update frontend `listCompanyDiscoveredContacts` in api.ts**

Find `listCompanyDiscoveredContacts` (line ~620). Replace `matchedOnly` with `titleMatch`:

```typescript
export async function listCompanyDiscoveredContacts(
  campaignId: string,
  companyId: string,
  options: { titleMatch?: boolean; provider?: string; search?: string; limit?: number; offset?: number } = {},
): Promise<DiscoveredContactListResponse> {
  const params = new URLSearchParams()
  params.set('campaign_id', campaignId)
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.provider) params.set('provider', options.provider)
  if (options.search) params.set('search', options.search)
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  return request<DiscoveredContactListResponse>(`/v1/companies/${companyId}/discovered-contacts?${params.toString()}`)
}
```

- [ ] **Step 7: Verify TypeScript**

```bash
cd apps/web && npx tsc --noEmit 2>&1
```

Expected: errors about `matchedOnly` callers in `usePipelineViews.ts` — those are fixed in Task 2. No errors inside `api.ts` itself.

- [ ] **Step 8: Commit**

```bash
git add app/api/routes/discovered_contacts.py apps/web/src/lib/api.ts
git commit -m "feat(contacts): replace matched_only with title_match on discovered contacts endpoint"
```

---

## Task 2: Fix S4RevealView — stale cancellation, reload wiring, disabled states

### Files
- Modify: `apps/web/src/hooks/usePipelineViews.ts`
- Modify: `apps/web/src/components/views/pipeline/S4RevealView.tsx`

- [ ] **Step 1: Add stale-request refs**

In `usePipelineViews.ts`, find the refs block around line 225 (near `s4RequestRef`, `s4ForegroundRequestRef`). Add two new refs right after them:

```typescript
const s4RevealRequestRef = useRef(0)
const s4RevealForegroundRequestRef = useRef(0)
```

- [ ] **Step 2: Rewrite `loadS4RevealView` with stale-cancellation and `titleMatch`**

Find `loadS4RevealView` (currently at line ~363). Replace it entirely:

```typescript
  const loadS4RevealView = useCallback(async () => {
    if (!requestsEnabled || !selectedCampaignId) {
      s4RevealRequestRef.current += 1
      setS4DiscoveredContacts(null)
      setS4DiscoveredCounts(null)
      setIsS4RevealLoading(false)
      return
    }
    const requestId = s4RevealRequestRef.current + 1
    s4RevealRequestRef.current = requestId
    s4RevealForegroundRequestRef.current = requestId
    setIsS4RevealLoading(true)
    try {
      const titleMatch =
        s4MatchFilter === 'matched' ? true :
        s4MatchFilter === 'unmatched' ? false :
        undefined
      const [contacts, counts] = await Promise.all([
        listDiscoveredContacts({
          campaignId: selectedCampaignId,
          titleMatch,
          limit: s4RevealPageSize,
          offset: s4RevealOffset,
        }),
        getDiscoveredContactCounts(selectedCampaignId),
      ])
      if (s4RevealRequestRef.current !== requestId) return
      setS4DiscoveredContacts(contacts)
      setS4DiscoveredCounts(counts)
    } catch (err) {
      if (s4RevealRequestRef.current !== requestId) return
      setError(parseApiError(err))
    } finally {
      if (s4RevealForegroundRequestRef.current === requestId) {
        setIsS4RevealLoading(false)
      }
    }
  }, [requestsEnabled, selectedCampaignId, s4MatchFilter, s4RevealOffset, s4RevealPageSize, setError])
```

- [ ] **Step 3: Add a stable ref for the view-change effect**

The view-change effect must call the _latest_ `loadS4RevealView` without having it as a dep (otherwise changing filter reruns the reset branch). Add a ref that tracks the latest version, just before `loadS4RevealView`:

```typescript
  const loadS4RevealViewRef = useRef(loadS4RevealView)
  useEffect(() => { loadS4RevealViewRef.current = loadS4RevealView }, [loadS4RevealView])
```

- [ ] **Step 4: Fix the view-change effect's `s4-reveal` branch**

Find the `useEffect` that handles view changes (currently at line ~438, deps: `[activeView, cancelStaleSelectAllRequests, loadPipelineView, loadFullPipelineView, loadS4RevealView, loadS4View]`).

Replace the `s4-reveal` branch:
```typescript
    } else if (activeView === 's4-reveal') {
      s4RevealRequestRef.current += 1  // invalidate any in-flight request from previous view
      setS4DiscoveredSelectedIds([])
      setS4MatchFilter('all')
      setS4RevealOffset(0)
      // loadS4RevealViewRef used here so this effect doesn't re-run when filter changes
      void loadS4RevealViewRef.current()
    } else if (activeView === 's5-validation') {
```

Remove `loadS4RevealView` from this effect's dependency array:
```typescript
  }, [activeView, cancelStaleSelectAllRequests, loadPipelineView, loadFullPipelineView, loadS4View])
```

- [ ] **Step 5: Add separate filter/offset reload effect**

Add this new `useEffect` after the view-change effect:

```typescript
  // Reload S4 reveal when filter or offset changes while on the view
  useEffect(() => {
    if (activeView !== 's4-reveal' || !selectedCampaignId) return
    void loadS4RevealView()
  }, [activeView, selectedCampaignId, s4MatchFilter, s4RevealOffset, loadS4RevealView])
```

- [ ] **Step 6: Add disabled states to S4RevealView.tsx**

In `S4RevealView.tsx`, make these changes:

**Filter chips** — find the `MATCH_FILTERS.map(...)` block. Add `disabled={isLoading}` to each button:
```tsx
{MATCH_FILTERS.map(({ value, label }) => (
  <button
    key={value}
    type="button"
    onClick={() => onMatchFilterChange(value)}
    disabled={isLoading}
    className="rounded-full border px-3 py-1 text-xs font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
    style={
      matchFilter === value
        ? { backgroundColor: 'var(--s4)', color: '#fff', borderColor: 'var(--s4)' }
        : { borderColor: 'var(--oc-border)', color: 'var(--oc-muted)' }
    }
  >
    {label}
  </button>
))}
```

**Select-all checkbox** — find the header `<input type="checkbox" ... onChange={() => onToggleAll(visibleIds)} ...>`. Add disabled:
```tsx
<input
  type="checkbox"
  checked={allVisibleSelected}
  onChange={() => onToggleAll(visibleIds)}
  disabled={isLoading || isRevealing}
  className="cursor-pointer disabled:cursor-not-allowed"
/>
```

**Row checkboxes** — find `<input type="checkbox" checked={selectedIds.includes(contact.id)} ...>`. Add disabled:
```tsx
<input
  type="checkbox"
  checked={selectedIds.includes(contact.id)}
  onChange={() => onToggle(contact.id)}
  onClick={(e) => e.stopPropagation()}
  disabled={isLoading || isRevealing}
  className="cursor-pointer disabled:cursor-not-allowed"
/>
```

**Pager** — find `<Pager ... onNext={onPageNext} />`. Add `disabled`:
```tsx
<Pager
  offset={offset}
  pageSize={pageSize}
  total={contacts?.total ?? null}
  hasMore={contacts?.has_more ?? false}
  onPrev={onPagePrev}
  onNext={onPageNext}
  disabled={isLoading}
/>
```

**SelectionBar** — find `<SelectionBar ... disabled={isRevealing}>`. Update:
```tsx
<SelectionBar
  stageColor="--s4"
  stageBg="--s4-bg"
  selectedCount={selectedIds.length}
  totalMatching={contacts?.total ?? 0}
  activeLetters={new Set()}
  onSelectAllMatching={null}
  isSelectingAll={false}
  onClear={onClearSelection}
  disabled={isLoading || isRevealing}
>
```

- [ ] **Step 7: Verify TypeScript**

```bash
cd apps/web && npx tsc --noEmit 2>&1
```

Expected: zero errors.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/hooks/usePipelineViews.ts apps/web/src/components/views/pipeline/S4RevealView.tsx
git commit -m "fix(s4-reveal): stale-request cancellation, backend-driven filter reloads, disabled states"
```

---

## Task 3: Fix S5ValidationView — disabled states

### Files
- Modify: `apps/web/src/components/views/pipeline/S4ValidationView.tsx`

No hook changes needed — backend wiring already works. `isLoading` and `isValidating` are already in the props interface and passed from App.tsx.

- [ ] **Step 1: Disable LetterStrip**

Find `<LetterStrip` (around line 224). Add `disabled`:
```tsx
<LetterStrip
  multiSelect
  activeLetters={activeLetters}
  counts={letterCounts}
  onToggle={onToggleLetter}
  onClear={onClearLetters}
  disabled={isLoading || isValidating}
/>
```

- [ ] **Step 2: Disable verification filter buttons**

Find the `VERIF_FILTERS.map(...)` block (around line 235). Add `disabled={isLoading}` to each button:
```tsx
{VERIF_FILTERS.map((f) => (
  <button
    key={f.value}
    type="button"
    onClick={() => onVerifFilterChange(f.value)}
    disabled={isLoading}
    className={`rounded-full px-3 py-1 text-[11px] font-bold transition disabled:opacity-50 disabled:cursor-not-allowed ${
      verifFilter === f.value
        ? 'text-white'
        : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s4) hover:text-(--s4-text)'
    }`}
    style={
      verifFilter === f.value
        ? { backgroundColor: f.color ?? 'var(--s4)' }
        : {}
    }
  >
    {f.label}
  </button>
))}
```

- [ ] **Step 3: Disable Pager**

Find `<Pager offset={offset} ... onPageSizeChange={onPageSizeChange} />` (line 255). Add `disabled`:
```tsx
<Pager
  offset={offset}
  pageSize={pageSize}
  total={contacts?.total ?? null}
  hasMore={contacts?.has_more ?? false}
  onPrev={onPagePrev}
  onNext={onPageNext}
  onPageSizeChange={onPageSizeChange}
  disabled={isLoading}
/>
```

- [ ] **Step 4: Disable SortableHeader columns**

Find the 5 `<SortableHeader` calls (lines 338–345). Add `disabled={isLoading}` to each:
```tsx
<SortableHeader label="Contact" field="first_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
<SortableHeader label="Company" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
<SortableHeader label="Modified" field="updated_at" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
<SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
<SortableHeader label="Verification" field="verification_status" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
<SortableHeader label="Stage" field="pipeline_stage" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
```

(Check the file — there may also be a `last_validated` header that is a plain `<th>`, not a SortableHeader — leave that as-is since it's not interactive.)

- [ ] **Step 5: Disable checkboxes**

**Header select-all** (around line 328):
```tsx
<input
  type="checkbox"
  checked={allVisibleSelected}
  ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
  onChange={() =>
    onToggleAll(allVisibleSelected ? [] : visibleContacts.map((c) => c.id))
  }
  disabled={isLoading || isValidating}
  className="cursor-pointer disabled:cursor-not-allowed"
/>
```

**Row checkboxes** (around line 360, inside the `visibleContacts.map`):
```tsx
<input
  type="checkbox"
  checked={selectedSet.has(contact.id)}
  onChange={() => onToggleContact(contact.id)}
  disabled={isLoading || isValidating}
  className="cursor-pointer disabled:cursor-not-allowed"
/>
```

- [ ] **Step 6: Verify TypeScript**

```bash
cd apps/web && npx tsc --noEmit 2>&1
```

Expected: zero errors. Check that `SortableHeader` accepts a `disabled` prop — if not, read its props interface and add it.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/views/pipeline/S4ValidationView.tsx
git commit -m "fix(s5-validation): disable all controls during loading"
```

---

## Task 4: TitleRulesPanel — seed button disabled state

### Files
- Modify: `apps/web/src/components/panels/TitleRulesPanel.tsx`

- [ ] **Step 1: Disable the seed button**

Find the "Seed default rules" button (line 333):
```tsx
<button
  type="button"
  onClick={() => void onSeedRules()}
  className="self-start rounded-xl border border-(--oc-border) px-3 py-1.5 text-xs font-medium text-(--oc-muted) transition hover:border-emerald-400 hover:text-emerald-800"
>
  Seed default rules
</button>
```

Replace with:
```tsx
<button
  type="button"
  onClick={() => void onSeedRules()}
  disabled={isLoading || isAdding}
  className="self-start rounded-xl border border-(--oc-border) px-3 py-1.5 text-xs font-medium text-(--oc-muted) transition hover:border-emerald-400 hover:text-emerald-800 disabled:opacity-50 disabled:cursor-not-allowed"
>
  Seed default rules
</button>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd apps/web && npx tsc --noEmit 2>&1
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/panels/TitleRulesPanel.tsx
git commit -m "fix(title-rules): disable seed button during load and add"
```

---

## Verification checklist

After all tasks:

1. `cd apps/web && npx tsc --noEmit` — zero errors
2. Backend: `GET /v1/discovered-contacts?campaign_id=X&title_match=false` returns only unmatched contacts
3. Backend: `GET /v1/discovered-contacts?campaign_id=X&title_match=true` returns only matched contacts
4. Backend: `GET /v1/discovered-contacts?campaign_id=X` (no title_match) returns all contacts
5. S4 Reveal: click "Unmatched" filter → new API call with `title_match=false`, only unmatched shown
6. S4 Reveal: rapid filter clicks → only the last request's data renders (stale responses discarded)
7. S4 Reveal: filter chips, checkboxes, Pager non-interactive while loading
8. S5 Validation: all 8 filter chips, LetterStrip, Pager, sort headers non-interactive while loading
9. TitleRulesPanel: "Seed default rules" button greyed while `isLoading` or `isAdding`
