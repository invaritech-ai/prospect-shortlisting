# A–Z Letter Navigation Design

Date: 2026-03-10

## Problem

The company list has no alphabetical ordering or quick-jump navigation. Colleagues want to sort companies lexicographically and jump to those starting with a given letter.

## Approach

**Letter filter (Approach A):** A–Z pill strip in the UI sends a `letter` query param to the backend. Backend filters to companies whose domain starts with that letter and sorts by `domain ASC`. All existing filters (decision, scrape) remain additive.

## Backend API

### `GET /v1/companies`

New optional query param: `letter: str | None = None`

When present:
- Appends `WHERE lower(left(domain, 1)) = lower(letter)`
- Overrides default sort to `ORDER BY domain ASC`

Default sort (no letter): `ORDER BY created_at DESC` (unchanged).

### `GET /v1/companies/letter-counts`

New endpoint. Query params: `decision_filter`, `scrape_filter` (same as `/v1/companies`).

Returns: `{"counts": {"a": 12, "b": 0, "c": 3, ...}}` — always 26 entries, zeros included.

Purpose: drives which letter pills are enabled/disabled in the UI.

### `GET /v1/companies/ids`

Existing endpoint gets a new `letter` param so "Select all matching" respects the active letter filter.

## Frontend UI

### Placement

Pill strip sits between the page header and the existing filter chips row:

```
┌────────────────────────────────────────────────────────┐
│  Companies  [Classify] [Export] [Select all]           │  header
├────────────────────────────────────────────────────────┤
│  All  A  B  C  D  E  F  G  H  I  J  K … Z             │  NEW
├────────────────────────────────────────────────────────┤
│  All · Qualified · Not qualified  |  Scraped · …       │  existing filters
└────────────────────────────────────────────────────────┘
```

### Pill states

| State | Visual |
|---|---|
| "All" active | accent background, white text |
| Letter with results, inactive | ghost pill, subtle border |
| Letter with results, active | accent background, white text |
| Letter with 0 results | no border, muted text, `cursor-not-allowed` |

No per-letter count badges — keeps the strip clean.

### Mobile

Horizontally scrollable single row (`overflow-x-auto`). Pills stay full size; user swipes to reach later letters. No wrapping.

### State management

- `letterFilter: string | null` in `App.tsx` alongside `decisionFilter` / `scrapeFilter`
- `letterCounts: Record<string, number>` in `App.tsx`
- Letter-counts fetched on mount and whenever `decisionFilter` or `scrapeFilter` changes
- Selecting a letter resets pagination offset to 0
- Passed as props to `CompaniesView`; component emits `onLetterChange`

### Sort behavior

- Letter active → `domain ASC` (backend-controlled, no UI toggle)
- "All" active → `created_at DESC` (default, unchanged)
