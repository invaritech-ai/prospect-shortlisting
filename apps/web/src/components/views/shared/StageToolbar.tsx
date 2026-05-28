/** Unified toolbar used by every stage view (S1, S2, S3, S5). */

interface StageFilter {
  value: string
  label: string
  count?: number
  color?: string        // defaults to stageColor when active
}

interface BulkAction {
  label: string
  onClick: () => void
}

interface StageToolbarProps {
  stageColor: string
  filters: StageFilter[]
  activeFilter: string
  onFilterChange: (value: string) => void
  search: string
  onSearchChange: (value: string) => void
  primaryAction?: { label: string; onClick: () => void }
  selectedCount?: number
  bulkActions?: BulkAction[]
  onClearSelection?: () => void
}

export function StageToolbar({
  stageColor, filters, activeFilter, onFilterChange,
  search, onSearchChange,
  primaryAction,
  selectedCount = 0, bulkActions = [], onClearSelection,
}: StageToolbarProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>

      {/* Row 1: filters + search + primary action — all on one line */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>

        {/* Filter pills */}
        <div style={{ display: 'flex', gap: '0.3125rem', flexWrap: 'wrap', flexShrink: 0 }}>
          {filters.map((f) => {
            const isActive = activeFilter === f.value
            const accent   = f.color ?? stageColor
            return (
              <button
                key={f.value}
                type="button"
                onClick={() => onFilterChange(f.value)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '0.3125rem',
                  padding: '0.375rem 0.75rem',
                  borderRadius: '9999px',
                  border: `1.5px solid ${isActive ? accent : 'var(--oc-border)'}`,
                  backgroundColor: isActive
                    ? `color-mix(in srgb, ${accent} 10%, var(--oc-surface))`
                    : 'var(--oc-surface)',
                  color: isActive ? accent : 'var(--oc-muted)',
                  fontWeight: isActive ? 700 : 500,
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  transition: 'all 150ms',
                  whiteSpace: 'nowrap',
                }}
              >
                {f.label}
                {f.count != null && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 700,
                    opacity: isActive ? 1 : 0.55,
                  }}>
                    {f.count}
                  </span>
                )}
              </button>
            )
          })}
        </div>

        {/* Search — expands to fill remaining space */}
        <div style={{ position: 'relative', flex: 1, minWidth: '140px', maxWidth: '280px' }}>
          <Search
            style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--oc-muted)', pointerEvents: 'none' }}
            size={13}
            strokeWidth={2.2}
          />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search domains…"
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: `0.375rem ${search ? '2rem' : '0.875rem'} 0.375rem 2.125rem`,
              borderRadius: '9999px',
              border: '1.5px solid var(--oc-border)',
              background: 'var(--oc-surface)',
              fontSize: '0.8125rem', fontFamily: 'inherit', color: 'var(--oc-text)',
              outline: 'none', transition: 'border-color 150ms',
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = stageColor }}
            onBlur={(e)  => { e.currentTarget.style.borderColor = 'var(--oc-border)' }}
          />
          {search && (
            <button
              type="button"
              onClick={() => onSearchChange('')}
              aria-label="Clear search"
              style={{
                position: 'absolute', right: '0.5rem', top: '50%', transform: 'translateY(-50%)',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: '18px', height: '18px', borderRadius: '9999px',
                border: 'none', background: 'var(--oc-muted)', color: '#fff',
                cursor: 'pointer', opacity: 0.55, transition: 'opacity 140ms', padding: 0, flexShrink: 0,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = '1' }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = '0.55' }}
            >
              <IconX size={8} />
            </button>
          )}
        </div>

        {/* Primary action */}
        {primaryAction && (
          <button
            type="button"
            onClick={primaryAction.onClick}
            style={{
              display: 'inline-flex', alignItems: 'center',
              padding: '0.375rem 0.875rem',
              borderRadius: '9999px',
              border: 'none',
              backgroundColor: stageColor, color: '#fff',
              fontWeight: 700, fontSize: '0.8125rem',
              cursor: 'pointer', fontFamily: 'inherit', transition: 'opacity 150ms',
              whiteSpace: 'nowrap', flexShrink: 0,
              boxShadow: `0 2px 6px color-mix(in srgb, ${stageColor} 30%, transparent)`,
            }}
          >
            {primaryAction.label}
          </button>
        )}

        {/* Bulk scrape/classify CTA (slides in when rows selected) */}
        {selectedCount > 0 && bulkActions.length === 0 && (
          <button
            type="button"
            onClick={onClearSelection}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
              padding: '0.375rem 0.875rem', borderRadius: '9999px',
              border: `1.5px solid ${stageColor}`,
              backgroundColor: `color-mix(in srgb, ${stageColor} 10%, var(--oc-surface))`,
              color: stageColor, fontWeight: 700, fontSize: '0.8125rem',
              cursor: 'pointer', fontFamily: 'inherit',
              animation: 'oc-fade-up 160ms ease', whiteSpace: 'nowrap', flexShrink: 0,
            }}
          >
            {selectedCount} selected · clear
          </button>
        )}
      </div>

      {/* Row 2: bulk label bar (only when selection + bulkActions provided) */}
      {selectedCount > 0 && bulkActions.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.625rem', flexWrap: 'wrap',
          padding: '0.625rem 0.875rem',
          backgroundColor: `color-mix(in srgb, ${stageColor} 7%, var(--oc-surface))`,
          border: `1.5px solid color-mix(in srgb, ${stageColor} 35%, var(--oc-border))`,
          borderRadius: '0.625rem',
          animation: 'oc-fade-up 180ms cubic-bezier(0.34,1.56,0.64,1)',
        }}>
          <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: stageColor, flexShrink: 0 }}>
            {selectedCount} selected
          </span>
          <div style={{ display: 'flex', gap: '0.3125rem', flexWrap: 'wrap' }}>
            {bulkActions.map((a) => (
              <button
                key={a.label}
                type="button"
                onClick={a.onClick}
                style={{
                  padding: '0.25rem 0.625rem', borderRadius: '9999px',
                  border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                  fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-text)',
                  cursor: 'pointer', fontFamily: 'inherit',
                }}
              >
                {a.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onClearSelection}
            style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', background: 'none', border: 'none', cursor: 'pointer', marginLeft: 'auto' }}
          >
            Clear
          </button>
        </div>
      )}
    </div>
  )
}
import { IconX } from '../../ui/icons'
import { Search } from 'lucide-react'
