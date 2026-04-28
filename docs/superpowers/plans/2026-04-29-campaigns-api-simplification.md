# Campaigns API Simplification

**Date:** 2026-04-29  
**Status:** Approved  
**Scope:** `app/api/routes/campaigns.py`, `app/api/schemas/campaign.py`

## Problem

1. `delete_campaign` and `assign_uploads_to_campaign` loop over uploads in Python and call `session.add` per row — should be single bulk SQL UPDATEs.
2. Count queries (upload_count, company_count) are duplicated inline across multiple handlers.
3. No `GET /campaigns/{campaign_id}` single-fetch endpoint.
4. No unassign-uploads endpoint — uploads can be assigned but never unassigned.
5. `assign_uploads_to_campaign` does not enforce the one-campaign-per-upload invariant.

## Business Rules

- An upload can belong to at most one campaign at a time.
- Assigning an upload that is already claimed by a *different* campaign must be rejected (409).
- Unassigning does not check ownership — clears campaign_id for all provided upload IDs unconditionally.
- Deleting a campaign unlinks its uploads (sets campaign_id = NULL); uploads and their data are preserved.

## Design

### 1. `_get_campaign_counts` helper

```python
def _get_campaign_counts(session, campaign_id) -> tuple[int, int]:
    # returns (upload_count, company_count)
```

Single place for both count queries. Used by assign, unassign, and the new single-fetch endpoint.

### 2. `delete_campaign` fix

Replace Python loop with:
```sql
UPDATE uploads SET campaign_id = NULL WHERE campaign_id = :campaign_id
```
Then delete the campaign and commit.

### 3. `assign_uploads_to_campaign` fix

Pre-flight 409 guard:
```sql
SELECT COUNT(*) FROM uploads
WHERE id IN (:upload_ids) AND campaign_id IS NOT NULL AND campaign_id != :campaign_id
```
If count > 0 → 409 "One or more uploads are already assigned to another campaign."

Bulk assign:
```sql
UPDATE uploads SET campaign_id = :campaign_id WHERE id IN (:upload_ids)
```

### 4. New: `GET /campaigns/{campaign_id}`

Returns `CampaignRead` (same shape as list items) with counts via `_get_campaign_counts`. 404 if not found.

### 5. New: `POST /campaigns/{campaign_id}/unassign-uploads`

Request: `CampaignAssignUploadsRequest` (reuse — same shape: `upload_ids: list[UUID]`).  
Bulk unassign:
```sql
UPDATE uploads SET campaign_id = NULL WHERE id IN (:upload_ids)
```
No ownership check. Returns updated `CampaignRead` via `_get_campaign_counts`.

## Files Changed

| File | Change |
|------|--------|
| `app/api/routes/campaigns.py` | Add `update` import, add helper, fix loops, add 2 endpoints |
| `app/api/schemas/campaign.py` | No changes needed — reuse existing schemas |
