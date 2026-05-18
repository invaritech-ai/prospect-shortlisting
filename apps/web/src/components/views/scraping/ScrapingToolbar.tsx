import { StageToolbar } from '../shared/StageToolbar'

export type StatusFilter = 'all' | 'pending' | 'running' | 'done' | 'failed'

const STATUS_FILTERS = [
  { value: 'all',     label: 'All'     },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running', color: 'var(--s1)' },
  { value: 'done',    label: 'Done',    color: 'var(--oc-success-text)' },
  { value: 'failed',  label: 'Failed',  color: 'var(--oc-fail-text)' },
]

interface ScrapingToolbarProps {
  statusFilter: StatusFilter
  search: string
  onStatusFilterChange: (f: StatusFilter) => void
  onSearchChange: (s: string) => void
  selectedCount: number
  hasFilterSelection: boolean
  onScrapeSelected: () => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  isBatchActive: boolean
  totalMatchingCount: number
}

export function ScrapingToolbar({
  statusFilter,
  search,
  onStatusFilterChange,
  onSearchChange,
  selectedCount,
  hasFilterSelection,
  onScrapeSelected,
  onSelectAllMatching,
  onClearSelection,
  isBatchActive,
  totalMatchingCount,
}: ScrapingToolbarProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <StageToolbar
        stageColor="var(--s1)"
        filters={STATUS_FILTERS}
        activeFilter={statusFilter}
        onFilterChange={(v) => onStatusFilterChange(v as StatusFilter)}
        search={search}
        onSearchChange={onSearchChange}
        primaryAction={
          selectedCount > 0 && !isBatchActive
            ? { label: `Scrape ${selectedCount.toLocaleString()} selected`, onClick: onScrapeSelected }
            : undefined
        }
        selectedCount={selectedCount}
        onClearSelection={onClearSelection}
      />

      {/* "Select all matching" + clear row */}
      {!isBatchActive && totalMatchingCount > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', paddingLeft: '0.125rem' }}>
          {!hasFilterSelection ? (
            <button
              type="button"
              onClick={onSelectAllMatching}
              style={{
                fontSize: '0.8125rem', fontWeight: 600, color: 'var(--s1)',
                background: 'none', border: 'none', cursor: 'pointer',
                textDecoration: 'underline', textUnderlineOffset: '2px',
                padding: 0,
              }}
            >
              Select all {totalMatchingCount.toLocaleString()} matching
            </button>
          ) : (
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
              All {totalMatchingCount.toLocaleString()} matching selected
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
