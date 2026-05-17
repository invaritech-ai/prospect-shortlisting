import type { MockScrapeRow } from '../../../lib/mockData'
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

interface ScrapingTableProps {
  rows: MockScrapeRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onRetry: (id: string) => void
  onViewDiagnostics: (row: MockScrapeRow) => void
}

export function ScrapingTable({ rows, selected, onToggleSelect, onToggleSelectAll, onRetry, onViewDiagnostics }: ScrapingTableProps) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))

  return (
    <div style={{ borderRadius: '0.875rem', border: '1px solid var(--oc-border)', overflow: 'hidden' }}>
      <table className="oc-compact-table">
        <thead>
          <tr>
            <th style={{ width: '2.5rem', paddingRight: 0 }}>
              <input
                type="checkbox"
                checked={allSelected}
                onChange={onToggleSelectAll}
                style={{ cursor: 'pointer', accentColor: 'var(--s1)', width: '1rem', height: '1rem' }}
                aria-label="Select all"
              />
            </th>
            <th>Domain</th>
            <th style={{ width: '110px' }}>Status</th>
            <th style={{ width: '80px' }}>Pages</th>
            <th style={{ width: '100px' }}>Updated</th>
            <th style={{ width: '80px' }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isSelected = selected.has(row.id)
            return (
              <tr
                key={row.id}
                style={{ background: isSelected ? 'color-mix(in srgb, var(--s1-bg) 60%, white)' : undefined, cursor: 'pointer' }}
                onClick={() => onViewDiagnostics(row)}
              >
                <td style={{ paddingRight: 0 }} onClick={(e) => { e.stopPropagation(); onToggleSelect(row.id) }}>
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleSelect(row.id)}
                    style={{ cursor: 'pointer', accentColor: 'var(--s1)', width: '1rem', height: '1rem' }}
                    aria-label={`Select ${row.domain}`}
                  />
                </td>
                <td>
                  <div>
                    <span style={{ fontWeight: 600, color: 'var(--oc-text)', fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}>
                      {row.domain}
                    </span>
                    {row.errorCode && (
                      <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--oc-fail-text)', marginTop: '0.125rem' }}>
                        {ERROR_LABELS[row.errorCode] ?? row.errorCode}
                      </span>
                    )}
                  </div>
                </td>
                <td><ScrapeStatusBadge status={row.status} /></td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: row.pagesCount > 0 ? 'var(--oc-text)' : 'var(--oc-muted)' }}>
                  {row.pagesCount > 0 ? row.pagesCount : '—'}
                </td>
                <td style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                  {relTime(row.updatedAt)}
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  {row.status === 'failed' && (
                    <button
                      type="button"
                      onClick={() => onRetry(row.id)}
                      className="oc-btn oc-btn-secondary oc-btn-xs"
                      style={{ borderColor: 'var(--s1)', color: 'var(--s1)' }}
                    >
                      Retry
                    </button>
                  )}
                  {row.status === 'pending' && (
                    <button
                      type="button"
                      onClick={() => onRetry(row.id)}
                      className="oc-btn oc-btn-secondary oc-btn-xs"
                    >
                      Scrape
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
