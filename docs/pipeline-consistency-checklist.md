# Pipeline Consistency Checklist

Use this checklist before merging any pipeline-facing change (S1/S2/S3/S4, Full Pipeline, or related API contracts).

## 1) Filter Semantics

- Declare each filter as one of:
  - server-backed (authoritative with pagination), or
  - client-local (page-local only).
- If client-local, make that scope explicit in UI copy and selection behavior.
- Ensure query params and UI controls use the same names and value casing.

## 2) Pagination and Totals

- `total` and `has_more` must reflect the same predicate used for returned items.
- Avoid mixing server pagination with hidden client-only predicates unless UX clearly labels page-local filtering.
- Verify offset/page size transitions keep stable result semantics.

## 3) Selection Invariants

- Guarantee `selectedCount <= trueMatchingCount`.
- “Select all matching” must use the same predicates as the visible list.
- When predicates are not server-representable, disable select-all-matching for that view.

## 4) Retry/Resume Policy

- Use one shared resume-stage precedence (S1 -> S2 -> S3).
- Keep permanent/soft failure policy consistent across S1 and Full Pipeline.
- If permanent retry is allowed, always show an explicit warning label.

## 5) Scope Semantics (`upload_id` / campaign)

- Verify list/count/stats endpoints agree on scope behavior.
- If an endpoint accepts scope params, it must apply them in query execution (not just echo).
- Add explicit tests for scoped and unscoped outputs.

## 6) Time and Enum Contracts

- Return UTC-safe datetimes (timezone-aware API read models).
- Normalize enum/status casing for frontend-safe comparisons.
- Avoid introducing mixed-case labels across equivalent endpoints.

## 7) Race Safety

- Add request generation guards to prevent stale responses overwriting fresh state.
- Remove duplicate fetch triggers for the same state transition.
- Verify rapid toggling (letters, paging, sort, view switch) preserves final UI correctness.

## 8) Regression Coverage

- Add/extend frontend API contract tests for new query/body serialization.
- Add backend route tests for filter + pagination + scope interactions.
- Add pure-function tests for brittle mapping logic (resume stage, filter mappings).
