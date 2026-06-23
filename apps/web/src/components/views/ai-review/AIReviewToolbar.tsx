import type { AIReviewRow, AIVerdict, AiReviewLabelCounts } from '../../../lib/types'
import { StageToolbar } from '../shared/StageToolbar'

type VerdictFilter = 'all' | AIVerdict
type AIReviewFilter = VerdictFilter | 'unclassified'

interface AIReviewToolbarProps {
  rows: AIReviewRow[]
  counts?: AiReviewLabelCounts | null
  filter: AIReviewFilter
  search: string
  selectedIds: Set<string>
  allMatchingSelected?: boolean
  matchingCount?: number
  isBatchActive?: boolean
  onFilterChange: (f: AIReviewFilter) => void
  onSearchChange: (s: string) => void
  onClassifyAll: () => void
  onSelectAllMatching: () => void
  onBulkLabel: (verdict: AIVerdict) => void
  onClearSelection: () => void
}

export function AIReviewToolbar({
  rows, counts: serverCounts, filter, search, selectedIds,
  allMatchingSelected = false, matchingCount = 0, isBatchActive = false,
  onFilterChange, onSearchChange, onClassifyAll, onSelectAllMatching, onBulkLabel, onClearSelection,
}: AIReviewToolbarProps) {
  const counts = {
    all: serverCounts?.all ?? rows.length,
    Unclassified: serverCounts?.unclassified ?? rows.filter((r) => r.verdict === 'Unclassified').length,
    Possible: serverCounts?.possible ?? rows.filter((r) => r.verdict === 'Possible').length,
    Unknown: serverCounts?.unknown ?? rows.filter((r) => r.verdict === 'Unknown').length,
    Crap: serverCounts?.crap ?? rows.filter((r) => r.verdict === 'Crap').length,
  }

  const FILTERS = [
    { value: 'all',      label: 'All',      count: counts.all },
    { value: 'unclassified', label: 'Unclassified', count: counts.Unclassified, color: 'var(--oc-muted)' },
    { value: 'Possible', label: 'Possible', count: counts.Possible, color: 'var(--s2)' },
    { value: 'Unknown',  label: 'Unknown',  count: counts.Unknown,  color: 'var(--oc-warn-text)' },
    { value: 'Crap',     label: 'Crap',     count: counts.Crap,     color: 'var(--oc-fail-text)' },
  ]

  const bulkActions = (['Possible', 'Unknown', 'Crap'] as AIVerdict[]).map((v) => ({
    label: `Mark ${v}`,
    onClick: () => onBulkLabel(v),
  }))
  if (allMatchingSelected && matchingCount > 0) {
    bulkActions.unshift({ label: `Classify ${matchingCount.toLocaleString()} matching`, onClick: onClassifyAll })
  } else if (selectedIds.size > 0) {
    bulkActions.unshift({ label: `Classify ${selectedIds.size} selected`, onClick: onClassifyAll })
  }

  const effectiveSelectedCount = allMatchingSelected ? matchingCount : selectedIds.size
  const primaryLabel = effectiveSelectedCount > 0
    ? `Classify ${effectiveSelectedCount.toLocaleString()} selected`
    : (filter === 'all' || filter === 'unclassified'
      ? 'Classify unclassified'
      : 'Classify matching')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <StageToolbar
        stageColor="var(--s2)"
        filters={FILTERS}
        activeFilter={filter}
        onFilterChange={(v) => onFilterChange(v as AIReviewFilter)}
        search={search}
        onSearchChange={onSearchChange}
        primaryAction={{ label: primaryLabel, onClick: onClassifyAll }}
        selectedCount={effectiveSelectedCount}
        bulkActions={bulkActions}
        onClearSelection={onClearSelection}
      />

      {!isBatchActive && matchingCount > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', paddingLeft: '0.125rem' }}>
          {!allMatchingSelected ? (
            <button
              type="button"
              onClick={onSelectAllMatching}
              style={{
                fontSize: '0.8125rem', fontWeight: 600, color: 'var(--s2)',
                background: 'none', border: 'none', cursor: 'pointer',
                textDecoration: 'underline', textUnderlineOffset: '2px',
                padding: 0,
              }}
            >
              Select all {matchingCount.toLocaleString()} matching
            </button>
          ) : (
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
              All {matchingCount.toLocaleString()} matching selected
              <button
                type="button"
                onClick={onClearSelection}
                style={{
                  marginLeft: '0.5rem', fontSize: '0.8125rem', fontWeight: 600,
                  color: 'var(--oc-fail-text)', background: 'none', border: 'none',
                  cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: '2px',
                  padding: 0,
                }}
              >
                Clear
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  )
}
