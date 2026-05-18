import type { MockScrapeRow } from '../../../lib/useAppData'
import { ScrapeStatusBadge } from '../shared/ScrapeStatusBadge'

function relTime(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (d < 1) return 'just now'
  if (d < 60) return `${d}m ago`
  return `${Math.floor(d / 60)}h ago`
}

const ERROR_LABELS: Record<string, string> = {
  TIMEOUT:   'Timed out',
  BOT_BLOCK: 'Bot blocked',
  NOT_FOUND: 'Page not found',
  DNS_ERROR: 'DNS failed',
}

interface ScrapingCardsProps {
  rows: MockScrapeRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onRetry: (id: string) => void
  onViewDiagnostics: (row: MockScrapeRow) => void
}

export function ScrapingCards({ rows, selected, onToggleSelect, onRetry, onViewDiagnostics }: ScrapingCardsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {rows.map((row) => {
        const isSelected = selected.has(row.id)
        return (
          <div
            key={row.id}
            className="oc-company-card"
            style={{
              borderColor: isSelected ? 'var(--s1)' : undefined,
              background: isSelected ? 'color-mix(in srgb, var(--s1-bg) 50%, white)' : undefined,
            }}
            onClick={() => onViewDiagnostics(row)}
          >
            {/* Top row: checkbox + domain + status */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleSelect(row.id)}
                onClick={(e) => e.stopPropagation()}
                style={{ cursor: 'pointer', accentColor: 'var(--s1)', width: '1.125rem', height: '1.125rem', flexShrink: 0 }}
                aria-label={`Select ${row.domain}`}
              />
              <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {row.domain}
              </span>
              <ScrapeStatusBadge status={row.status} />
            </div>

            {/* Detail row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '0.5rem', paddingLeft: '1.875rem' }}>
              {row.errorCode ? (
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-fail-text)', fontWeight: 500 }}>
                  {ERROR_LABELS[row.errorCode] ?? row.errorCode}
                </span>
              ) : row.status === 'done' ? (
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--oc-text)' }}>{row.pagesCount}</span> pages
                </span>
              ) : row.status === 'running' ? (
                <span style={{ fontSize: '0.8125rem', color: 'var(--s1)', fontWeight: 500 }}>Scraping now…</span>
              ) : (
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>Waiting in queue</span>
              )}
              <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginLeft: 'auto' }}>{relTime(row.updatedAt)}</span>

              {(row.status === 'failed' || row.status === 'pending') && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onRetry(row.id) }}
                  className="oc-btn oc-btn-secondary oc-btn-xs"
                  style={{ flexShrink: 0, borderColor: 'var(--s1)', color: 'var(--s1)' }}
                >
                  {row.status === 'failed' ? 'Retry' : 'Scrape'}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
