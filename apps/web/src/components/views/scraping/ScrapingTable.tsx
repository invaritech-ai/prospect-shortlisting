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

interface ScrapingTableProps {
  rows: MockScrapeRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onRetry: (id: string) => void
  onViewContent: (row: MockScrapeRow) => void
  hasActiveFilter?: boolean
  onClearFilter?: () => void
}

export function ScrapingTable({ rows, selected, onToggleSelect, onToggleSelectAll, onRetry, onViewContent, hasActiveFilter, onClearFilter }: ScrapingTableProps) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))

  return (
    <div className="oc-panel" style={{ overflow: 'hidden', padding: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="oc-compact-table" style={{ minWidth: '640px' }}>
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
              <th style={{ width: '64px', textAlign: 'center' }}>Pages</th>
              <th style={{ width: '90px' }}>Updated</th>
              <th style={{ width: '120px' }} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginBottom: '0.625rem' }}>
                    {hasActiveFilter ? 'No companies match this filter.' : 'No companies scraped yet.'}
                  </div>
                  {hasActiveFilter && onClearFilter && (
                    <button type="button" onClick={onClearFilter}
                      style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--s1)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: '2px' }}>
                      Clear filter
                    </button>
                  )}
                  {!hasActiveFilter && (
                    <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>Import a spreadsheet from the Campaigns view to get started.</span>
                  )}
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const isSelected = selected.has(row.id)
              return (
                <tr
                  key={row.id}
                  style={{ background: isSelected ? 'color-mix(in srgb, var(--s1-bg) 60%, white)' : undefined }}
                >
                  {/* Checkbox */}
                  <td style={{ paddingRight: 0 }} onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleSelect(row.id)}
                      style={{ cursor: 'pointer', accentColor: 'var(--s1)', width: '1rem', height: '1rem' }}
                      aria-label={`Select ${row.domain}`}
                    />
                  </td>

                  {/* Domain — clickable link */}
                  <td>
                    <div>
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          fontWeight: 600, color: 'var(--oc-text)',
                          fontFamily: 'var(--font-mono)', fontSize: '0.875rem',
                          textDecoration: 'none', borderBottom: '1px dashed var(--oc-border)',
                          transition: 'color 120ms, border-color 120ms',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--s1)'; e.currentTarget.style.borderBottomColor = 'var(--s1)' }}
                        onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-text)'; e.currentTarget.style.borderBottomColor = 'var(--oc-border)' }}
                      >
                        {row.domain}
                        <svg style={{ display: 'inline', marginLeft: '0.25rem', verticalAlign: 'middle', opacity: 0.4 }} width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                      </a>
                      {row.errorCode && (
                        <span style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--oc-fail-text)', marginTop: '0.125rem', fontWeight: 500 }}>
                          {ERROR_LABELS[row.errorCode] ?? row.errorCode}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Status */}
                  <td><ScrapeStatusBadge status={row.status} /></td>

                  {/* Pages */}
                  <td style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: row.pagesCount > 0 ? 'var(--oc-text)' : 'var(--oc-muted)' }}>
                    {row.pagesCount > 0 ? row.pagesCount : '—'}
                  </td>

                  {/* Updated */}
                  <td style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {relTime(row.updatedAt)}
                  </td>

                  {/* Actions */}
                  <td onClick={(e) => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: '0.375rem', justifyContent: 'flex-end' }}>
                      {row.status === 'done' && (
                        <button
                          type="button"
                          onClick={() => onViewContent(row)}
                          aria-label={`View scraped content for ${row.domain}`}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                            fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)',
                            cursor: 'pointer', fontFamily: 'inherit', transition: 'all 140ms',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--s1)'; e.currentTarget.style.borderColor = 'var(--s1)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-muted)'; e.currentTarget.style.borderColor = 'var(--oc-border)' }}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                          View
                        </button>
                      )}
                      {row.status === 'failed' && (
                        <button
                          type="button"
                          onClick={() => onRetry(row.id)}
                          aria-label={`Retry scraping ${row.domain}`}
                          style={{
                            display: 'inline-flex', alignItems: 'center',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: '1.5px solid var(--s1)', background: 'var(--s1-bg)',
                            fontSize: '0.75rem', fontWeight: 600, color: 'var(--s1)',
                            cursor: 'pointer', fontFamily: 'inherit',
                          }}
                        >
                          Retry
                        </button>
                      )}
                      {row.status === 'pending' && (
                        <button
                          type="button"
                          onClick={() => onRetry(row.id)}
                          aria-label={`Scrape ${row.domain}`}
                          style={{
                            display: 'inline-flex', alignItems: 'center',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                            fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)',
                            cursor: 'pointer', fontFamily: 'inherit',
                          }}
                        >
                          Scrape
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
