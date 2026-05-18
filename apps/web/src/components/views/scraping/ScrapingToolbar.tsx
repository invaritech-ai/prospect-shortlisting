import { StageToolbar } from '../shared/StageToolbar'
import type { ScrapeStatus } from '../../../lib/useAppData'

export type FilterValue = ScrapeStatus | 'all'

const FILTERS = [
  { value: 'all',     label: 'All'     },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running', color: 'var(--s1)' },
  { value: 'done',    label: 'Done',    color: 'var(--oc-success-text)' },
  { value: 'failed',  label: 'Failed',  color: 'var(--oc-fail-text)' },
]

interface ScrapingToolbarProps {
  filter: FilterValue
  search: string
  onFilterChange: (f: FilterValue) => void
  onSearchChange: (s: string) => void
  selectedCount: number
  onScrapeSelected: () => void
}

export function ScrapingToolbar({ filter, search, onFilterChange, onSearchChange, selectedCount, onScrapeSelected }: ScrapingToolbarProps) {
  return (
    <StageToolbar
      stageColor="var(--s1)"
      filters={FILTERS}
      activeFilter={filter}
      onFilterChange={(v) => onFilterChange(v as FilterValue)}
      search={search}
      onSearchChange={onSearchChange}
      primaryAction={selectedCount > 0 ? { label: `Scrape ${selectedCount} selected`, onClick: onScrapeSelected } : undefined}
      selectedCount={selectedCount}
      onClearSelection={() => onFilterChange('all')}
    />
  )
}
