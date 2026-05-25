import type { DomainRead } from '../../../lib/types'
import { ScrapeStatusBadge } from '../shared/ScrapeStatusBadge'

function relTime(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime()) / 60_000)
  if (d < 1) return 'just now'
  if (d < 60) return `${d}m ago`
  return `${Math.floor(d / 60)}h ago`
}

function failureLabel(row: DomainRead): string | null {
  if ((row.scrape_status ?? 'pending') !== 'failed') return null
  const cls = row.latest_scrape_failure_class
  if (cls === 'permanent') return 'Permanent'
  if (cls === 'transient') return 'Transient'
  if (cls === 'blocked') return 'Blocked'
  if (cls === 'no_content') return 'No content'
  return row.latest_scrape_error_code ?? null
}

interface ScrapingCardsProps {
  rows: DomainRead[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onScrapeOne: (d: DomainRead) => void
  onViewContent: (d: DomainRead) => void
  isScrapeDisabled?: boolean
}

export function ScrapingCards({ rows, selected, onToggleSelect, onScrapeOne, onViewContent, isScrapeDisabled = false }: ScrapingCardsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {rows.map((row) => {
        const isSelected = selected.has(row.id)
        const status = row.scrape_status ?? 'pending'
        return (
          <div
            key={row.id}
            className="oc-company-card"
            style={{
              borderColor: isSelected ? 'var(--s1)' : undefined,
              background: isSelected ? 'color-mix(in srgb, var(--s1-bg) 50%, white)' : undefined,
            }}
            onClick={() => status === 'succeeded' ? onViewContent(row) : undefined}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleSelect(row.id)}
                onClick={(e) => e.stopPropagation()}
                style={{ cursor: 'pointer', accentColor: 'var(--s1)', width: '1.125rem', height: '1.125rem', flexShrink: 0 }}
              />
              <span style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {row.domain}
              </span>
              <ScrapeStatusBadge status={status} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '0.5rem', paddingLeft: '1.875rem' }}>
              {status === 'succeeded' ? (
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>Scraped</span>
              ) : status === 'running' || status === 'queued' ? (
                <span style={{ fontSize: '0.8125rem', color: 'var(--s1)', fontWeight: 500 }}>Scraping…</span>
              ) : status === 'failed' ? (
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-fail-text)', fontWeight: 500 }}>
                  {failureLabel(row) ?? 'Failed'}
                </span>
              ) : (
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>Pending</span>
              )}
              <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginLeft: 'auto' }}>
                {relTime(row.latest_scrape_updated_at ?? row.created_at)}
              </span>
              {(status === 'failed' || status === 'pending' || status == null) && (
                <button
                  type="button"
                  disabled={isScrapeDisabled}
                  onClick={(e) => {
                    e.stopPropagation()
                    if (!isScrapeDisabled) onScrapeOne(row)
                  }}
                  className="oc-btn oc-btn-secondary oc-btn-xs"
                  style={{
                    flexShrink: 0,
                    borderColor: 'var(--s1)',
                    color: 'var(--s1)',
                    opacity: isScrapeDisabled ? 0.45 : 1,
                    cursor: isScrapeDisabled ? 'not-allowed' : 'pointer',
                  }}
                >
                  {status === 'failed' ? 'Retry' : 'Scrape'}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
