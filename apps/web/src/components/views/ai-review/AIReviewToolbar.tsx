import type { AIVerdict, MockAIRow } from '../../../lib/useAppData'
import type { AiReviewLabelCounts } from '../../../lib/types'
import { StageToolbar } from '../shared/StageToolbar'

type VerdictFilter = 'all' | AIVerdict
type AIReviewFilter = VerdictFilter | 'unclassified'

interface AIReviewToolbarProps {
  rows: MockAIRow[]
  counts?: AiReviewLabelCounts | null
  filter: AIReviewFilter
  search: string
  selectedIds: Set<string>
  onFilterChange: (f: AIReviewFilter) => void
  onSearchChange: (s: string) => void
  onClassifyAll: () => void
  onBulkLabel: (verdict: AIVerdict) => void
  onClearSelection: () => void
}

export function AIReviewToolbar({
  rows, counts: serverCounts, filter, search, selectedIds,
  onFilterChange, onSearchChange, onClassifyAll, onBulkLabel, onClearSelection,
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
  if (selectedIds.size > 0) {
    bulkActions.unshift({ label: `Classify ${selectedIds.size} selected`, onClick: onClassifyAll })
  }

  return (
    <StageToolbar
      stageColor="var(--s2)"
      filters={FILTERS}
      activeFilter={filter}
      onFilterChange={(v) => onFilterChange(v as AIReviewFilter)}
      search={search}
      onSearchChange={onSearchChange}
      primaryAction={{ label: 'Classify unreviewed', onClick: onClassifyAll }}
      selectedCount={selectedIds.size}
      bulkActions={bulkActions}
      onClearSelection={onClearSelection}
    />
  )
}
