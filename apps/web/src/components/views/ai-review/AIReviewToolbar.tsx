import type { AIVerdict, MockAIRow } from '../../../lib/useAppData'
import { StageToolbar } from '../shared/StageToolbar'

type VerdictFilter = 'all' | AIVerdict

interface AIReviewToolbarProps {
  rows: MockAIRow[]
  filter: VerdictFilter
  search: string
  selectedIds: Set<string>
  onFilterChange: (f: VerdictFilter) => void
  onSearchChange: (s: string) => void
  onClassifyAll: () => void
  onBulkLabel: (verdict: AIVerdict) => void
  onClearSelection: () => void
}

export function AIReviewToolbar({
  rows, filter, search, selectedIds,
  onFilterChange, onSearchChange, onClassifyAll, onBulkLabel, onClearSelection,
}: AIReviewToolbarProps) {
  const counts = {
    all:      rows.length,
    Possible: rows.filter((r) => r.verdict === 'Possible').length,
    Unknown:  rows.filter((r) => r.verdict === 'Unknown').length,
    Crap:     rows.filter((r) => r.verdict === 'Crap').length,
  }

  const FILTERS = [
    { value: 'all',      label: 'All',      count: counts.all },
    { value: 'Possible', label: 'Possible', count: counts.Possible, color: 'var(--s2)' },
    { value: 'Unknown',  label: 'Unknown',  count: counts.Unknown,  color: 'var(--oc-warn-text)' },
    { value: 'Crap',     label: 'Crap',     count: counts.Crap,     color: 'var(--oc-fail-text)' },
  ]

  const bulkActions = (['Possible', 'Unknown', 'Crap'] as AIVerdict[]).map((v) => ({
    label: `Mark ${v}`,
    onClick: () => onBulkLabel(v),
  }))

  return (
    <StageToolbar
      stageColor="var(--s2)"
      filters={FILTERS}
      activeFilter={filter}
      onFilterChange={(v) => onFilterChange(v as VerdictFilter)}
      search={search}
      onSearchChange={onSearchChange}
      primaryAction={{ label: 'Classify unreviewed', onClick: onClassifyAll }}
      selectedCount={selectedIds.size}
      bulkActions={bulkActions}
      onClearSelection={onClearSelection}
    />
  )
}
