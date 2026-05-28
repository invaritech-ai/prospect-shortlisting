import type { DomainRead } from '../../../lib/types'
import { ScrapeStatusBadge } from '../shared/ScrapeStatusBadge'
import { IconExternalLink, IconEye } from '../../ui/icons'

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

interface ScrapingTableProps {
  rows: DomainRead[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onScrapeOne: (d: DomainRead) => void
  onViewContent: (d: DomainRead) => void
  isScrapeDisabled?: boolean
  hasActiveFilter?: boolean
  onClearFilter?: () => void
}

export function ScrapingTable({
  rows, selected, onToggleSelect, onToggleSelectAll,
  onScrapeOne, onViewContent, isScrapeDisabled = false, hasActiveFilter, onClearFilter,
}: ScrapingTableProps) {
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
              <th style={{ width: '90px' }}>Updated</th>
              <th style={{ width: '120px' }} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginBottom: '0.625rem' }}>
                    {hasActiveFilter ? 'No domains match this filter.' : 'No domains yet.'}
                  </div>
                  {hasActiveFilter && onClearFilter && (
                    <button type="button" onClick={onClearFilter}
                      style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--s1)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: '2px' }}>
                      Clear filter
                    </button>
                  )}
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const isSelected = selected.has(row.id)
              const status = row.scrape_status ?? 'pending'
              return (
                <tr
                  key={row.id}
                  style={{ background: isSelected ? 'color-mix(in srgb, var(--s1-bg) 60%, white)' : undefined }}
                >
                  <td style={{ paddingRight: 0 }} onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleSelect(row.id)}
                      style={{ cursor: 'pointer', accentColor: 'var(--s1)', width: '1rem', height: '1rem' }}
                    />
                  </td>

                  <td>
                    <a
                      href={row.normalized_url}
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
                      <IconExternalLink style={{ display: 'inline', marginLeft: '0.25rem', verticalAlign: 'middle', opacity: 0.4 }} size={10} />
                    </a>
                  </td>

                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', alignItems: 'flex-start' }}>
                      <ScrapeStatusBadge status={status} />
                      {failureLabel(row) && (
                        <span
                          title={row.latest_scrape_error_code ?? undefined}
                          style={{ fontSize: '0.68rem', color: 'var(--oc-muted)', fontWeight: 600 }}
                        >
                          {failureLabel(row)}
                        </span>
                      )}
                    </div>
                  </td>

                  <td style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {relTime(row.latest_scrape_updated_at ?? row.created_at)}
                  </td>

                  <td onClick={(e) => e.stopPropagation()}>
                    <div style={{ display: 'flex', gap: '0.375rem', justifyContent: 'flex-end' }}>
                      {status === 'succeeded' && (
                        <button
                          type="button"
                          onClick={() => onViewContent(row)}
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
                          <IconEye size={12} />
                          View
                        </button>
                      )}
                      {(status === 'failed' || status === 'pending' || status == null) && (
                        <button
                          type="button"
                          disabled={isScrapeDisabled}
                          onClick={() => {
                            if (!isScrapeDisabled) onScrapeOne(row)
                          }}
                          style={{
                            display: 'inline-flex', alignItems: 'center',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: status === 'failed' ? '1.5px solid var(--s1)' : '1.5px solid var(--oc-border)',
                            background: status === 'failed' ? 'var(--s1-bg)' : 'var(--oc-surface)',
                            fontSize: '0.75rem', fontWeight: 600,
                            color: status === 'failed' ? 'var(--s1)' : 'var(--oc-muted)',
                            cursor: isScrapeDisabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                            opacity: isScrapeDisabled ? 0.45 : 1,
                          }}
                        >
                          {status === 'failed' ? 'Retry' : 'Scrape'}
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
