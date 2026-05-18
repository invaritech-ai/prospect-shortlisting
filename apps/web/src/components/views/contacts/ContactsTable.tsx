import type { MockContactRow } from '../../../lib/useAppData'
import { ContactStatusBadge } from './ContactStatusBadge'

function relTime(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (d < 1) return 'just now'
  if (d < 60) return `${d}m ago`
  return `${Math.floor(d / 60)}h ago`
}

interface ContactsTableProps {
  rows: MockContactRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onFetch: (id: string) => void
  onViewContacts: (row: MockContactRow) => void
  hasActiveFilter?: boolean
  onClearFilter?: () => void
}

export function ContactsTable({ rows, selected, onToggleSelect, onToggleSelectAll, onFetch, onViewContacts, hasActiveFilter, onClearFilter }: ContactsTableProps) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))

  return (
    <div className="oc-panel" style={{ overflow: 'hidden', padding: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="oc-compact-table" style={{ minWidth: '620px' }}>
          <thead>
            <tr>
              <th style={{ width: '2.5rem', paddingLeft: '1rem' }}>
                <input type="checkbox" checked={allSelected} onChange={onToggleSelectAll} style={{ accentColor: 'var(--s3)' }} />
              </th>
              <th>Domain</th>
              <th style={{ width: '110px' }}>Status</th>
              <th style={{ width: '80px', textAlign: 'center' }}>Contacts</th>
              <th style={{ width: '72px', textAlign: 'center' }}>Emails</th>
              <th style={{ width: '80px' }}>Updated</th>
              <th style={{ width: '140px' }} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginBottom: '0.625rem' }}>
                    {hasActiveFilter ? 'No companies match this filter.' : 'No contacts discovered yet.'}
                  </div>
                  {hasActiveFilter && onClearFilter && (
                    <button type="button" onClick={onClearFilter}
                      style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--s3)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: '2px' }}>
                      Clear filter
                    </button>
                  )}
                  {!hasActiveFilter && (
                    <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>Companies classified as Possible in S2 will appear here ready for contact discovery.</span>
                  )}
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const isSelected = selected.has(row.id)
              return (
                <tr key={row.id} style={{ backgroundColor: isSelected ? 'color-mix(in srgb, var(--s3) 5%, transparent)' : undefined }}>

                  {/* Checkbox */}
                  <td style={{ paddingLeft: '1rem' }}>
                    <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(row.id)} style={{ accentColor: 'var(--s3)' }} />
                  </td>

                  {/* Domain */}
                  <td>
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontFamily: 'var(--font-mono)', fontSize: '0.875rem', fontWeight: 600,
                        color: 'var(--oc-text)', textDecoration: 'none',
                        borderBottom: '1px dashed var(--oc-border)',
                        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                        transition: 'color 120ms, border-color 120ms',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--s3)'; e.currentTarget.style.borderBottomColor = 'var(--s3)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-text)'; e.currentTarget.style.borderBottomColor = 'var(--oc-border)' }}
                    >
                      {row.domain}
                      <svg style={{ opacity: 0.4 }} width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                    </a>
                  </td>

                  {/* Status */}
                  <td><ContactStatusBadge status={row.status} /></td>

                  {/* Contacts — clickable when available */}
                  <td style={{ textAlign: 'center' }}>
                    {row.contactsFound > 0 && row.status === 'done' ? (
                      <button
                        type="button"
                        onClick={() => onViewContacts(row)}
                        aria-label={`View ${row.contactsFound} contacts for ${row.domain}`}
                        style={{
                          fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 700,
                          color: 'var(--s3)', background: 'none', border: 'none',
                          cursor: 'pointer', padding: '0.25rem 0.375rem',
                          borderRadius: '0.375rem', transition: 'background 140ms',
                          textDecoration: 'underline', textDecorationStyle: 'dotted',
                          textUnderlineOffset: '2px',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--s3-bg)' }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
                      >
                        {row.contactsFound}
                      </button>
                    ) : (
                      <span style={{ color: 'var(--oc-muted)', fontSize: '0.875rem' }}>—</span>
                    )}
                  </td>

                  {/* Emails */}
                  <td style={{ textAlign: 'center' }}>
                    {row.emailsFound > 0 ? (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 700, color: 'var(--oc-success-text)' }}>
                        {row.emailsFound}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--oc-muted)', fontSize: '0.875rem' }}>—</span>
                    )}
                  </td>

                  {/* Updated */}
                  <td style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {relTime(row.updatedAt)}
                  </td>

                  {/* Actions */}
                  <td>
                    <div style={{ display: 'flex', gap: '0.375rem', justifyContent: 'flex-end' }}>
                      {row.status === 'done' && row.contactsFound > 0 && (
                        <button
                          type="button"
                          onClick={() => onViewContacts(row)}
                          aria-label={`View ${row.contactsFound} contacts for ${row.domain}`}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: '1.5px solid var(--s3)',
                            background: 'var(--s3-bg)',
                            fontSize: '0.75rem', fontWeight: 700, color: 'var(--s3)',
                            cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
                            transition: 'all 140ms',
                          }}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                          View contacts
                        </button>
                      )}
                      {(row.status === 'pending' || row.status === 'failed') && (
                        <button
                          type="button"
                          onClick={() => onFetch(row.id)}
                          aria-label={`${row.status === 'failed' ? 'Retry fetching' : 'Fetch'} contacts for ${row.domain}`}
                          style={{
                            display: 'inline-flex', alignItems: 'center',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                            fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)',
                            cursor: 'pointer', fontFamily: 'inherit',
                            transition: 'all 140ms',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--s3)'; e.currentTarget.style.color = 'var(--s3)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)'; e.currentTarget.style.color = 'var(--oc-muted)' }}
                        >
                          {row.status === 'failed' ? 'Retry' : 'Fetch'}
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
