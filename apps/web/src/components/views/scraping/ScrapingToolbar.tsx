import type { ScrapeStatus } from '../../../lib/mockData'

type FilterValue = ScrapeStatus | 'all'

const FILTERS: { value: FilterValue; label: string }[] = [
  { value: 'all',     label: 'All'     },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'done',    label: 'Done'    },
  { value: 'failed',  label: 'Failed'  },
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
    <div className="oc-toolbar" style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
      {/* Filter pills */}
      <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap' }}>
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => onFilterChange(f.value)}
            style={{
              borderRadius: '9999px',
              padding: '0.375rem 0.875rem',
              fontSize: '0.8125rem',
              fontWeight: filter === f.value ? 700 : 500,
              cursor: 'pointer',
              border: '1px solid',
              fontFamily: 'inherit',
              transition: 'all 160ms',
              borderColor: filter === f.value ? 'var(--s1)' : 'var(--oc-border)',
              background:  filter === f.value ? 'var(--s1-bg)' : 'var(--oc-surface)',
              color:       filter === f.value ? 'var(--s1)'    : 'var(--oc-muted)',
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Search */}
      <input
        type="search"
        placeholder="Search domains…"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        style={{
          flex: 1, minWidth: '140px', maxWidth: '260px',
          borderRadius: '9999px',
          border: '1px solid var(--oc-border)',
          background: 'var(--oc-surface)',
          padding: '0.375rem 0.875rem',
          fontSize: '0.875rem',
          fontFamily: 'inherit',
          color: 'var(--oc-text)',
          outline: 'none',
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--s1)' }}
        onBlur={(e)  => { e.currentTarget.style.borderColor = 'var(--oc-border)' }}
      />

      {/* Bulk action — slides in when something is selected */}
      {selectedCount > 0 && (
        <button
          type="button"
          onClick={onScrapeSelected}
          className="oc-btn oc-btn-sm"
          style={{ backgroundColor: 'var(--s1)', color: '#fff', borderColor: 'var(--s1)', marginLeft: 'auto', flexShrink: 0, animation: 'oc-fade-up 160ms ease' }}
        >
          Scrape {selectedCount} selected
        </button>
      )}
    </div>
  )
}

export type { FilterValue }
