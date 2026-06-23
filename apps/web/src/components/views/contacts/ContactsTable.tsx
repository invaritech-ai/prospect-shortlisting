import type { EmailFetchCompanyRow } from '../../../lib/types'
import { ContactStatusBadge } from './ContactStatusBadge'
import { SortableHeader } from '../../ui/SortableHeader'
import { formatRelativeTime as relTime } from '../shared/relativeTime'
import { ExternalLink, RefreshCw, Users } from 'lucide-react'

interface ContactsTableProps {
  rows: EmailFetchCompanyRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onFetch: (id: string) => void
  onRefetch: (id: string) => void
  onViewContacts: (row: EmailFetchCompanyRow) => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
  fetchDisabled?: boolean
  hasActiveFilter?: boolean
  onClearFilter?: () => void
}

export function ContactsTable({ rows, selected, onToggleSelect, onToggleSelectAll, onFetch, onRefetch, onViewContacts, sortBy, sortDir, onSort, fetchDisabled = false, hasActiveFilter, onClearFilter }: ContactsTableProps) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.domain_id))

  return (
    <div className="oc-panel" style={{ overflow: 'hidden', padding: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="oc-compact-table" style={{ minWidth: '700px' }}>
          <thead>
            <tr>
              <th style={{ width: '2.5rem', paddingLeft: '1rem' }}>
                <input type="checkbox" checked={allSelected} onChange={onToggleSelectAll} style={{ accentColor: 'var(--s3)' }} />
              </th>
              <SortableHeader label="Domain" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Status" field="status" sortBy={sortBy} sortDir={sortDir} onSort={onSort} style={{ width: '110px' }} />
              <SortableHeader label="Fetched" field="fetched" sortBy={sortBy} sortDir={sortDir} onSort={onSort} style={{ width: '80px', textAlign: 'center' }} />
              <SortableHeader label="Contacts" field="contacts" sortBy={sortBy} sortDir={sortDir} onSort={onSort} style={{ width: '80px', textAlign: 'center' }} />
              <SortableHeader label="Emails" field="emails" sortBy={sortBy} sortDir={sortDir} onSort={onSort} style={{ width: '72px', textAlign: 'center' }} />
              <SortableHeader label="Updated" field="updated" sortBy={sortBy} sortDir={sortDir} onSort={onSort} style={{ width: '80px' }} />
              <th style={{ width: '210px' }} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
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
              const isSelected = selected.has(row.domain_id)
              return (
                <tr key={row.domain_id} style={{ backgroundColor: isSelected ? 'color-mix(in srgb, var(--s3) 5%, transparent)' : undefined }}>

                  {/* Checkbox */}
                  <td style={{ paddingLeft: '1rem' }}>
                    <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(row.domain_id)} style={{ accentColor: 'var(--s3)' }} />
                  </td>

                  {/* Domain */}
                  <td>
                    <a
                      href={row.normalized_url}
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
                      <ExternalLink size={9} strokeWidth={2.5} style={{ opacity: 0.4 }} />
                    </a>
                  </td>

                  {/* Status */}
                  <td><ContactStatusBadge status={row.status} /></td>

                  {/* Fetched people */}
                  <td style={{ textAlign: 'center' }}>
                    {row.fetched_people_found > 0 ? (
                      <button
                        type="button"
                        onClick={() => onViewContacts(row)}
                        aria-label={`View ${row.fetched_people_found} fetched people for ${row.domain}`}
                        style={{
                          fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 700,
                          color: 'var(--oc-muted)', background: 'none', border: 'none',
                          cursor: 'pointer', padding: '0.25rem 0.375rem',
                          borderRadius: '0.375rem', transition: 'background 140ms',
                          textDecoration: 'underline', textDecorationStyle: 'dotted',
                          textUnderlineOffset: '2px',
                        }}
                      >
                        {row.fetched_people_found}
                      </button>
                    ) : (
                      <span style={{ color: 'var(--oc-muted)', fontSize: '0.875rem' }}>—</span>
                    )}
                  </td>

                  {/* Contacts — clickable when available */}
                  <td style={{ textAlign: 'center' }}>
                    {row.contacts_found > 0 && row.status === 'done' ? (
                      <button
                        type="button"
                        onClick={() => onViewContacts(row)}
                        aria-label={`View ${row.contacts_found} contacts for ${row.domain}`}
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
                        {row.contacts_found}
                      </button>
                    ) : (
                      <span style={{ color: 'var(--oc-muted)', fontSize: '0.875rem' }}>—</span>
                    )}
                  </td>

                  {/* Emails */}
                  <td style={{ textAlign: 'center' }}>
                    {row.emails_found > 0 ? (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 700, color: 'var(--oc-success-text)' }}>
                        {row.emails_found}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--oc-muted)', fontSize: '0.875rem' }}>—</span>
                    )}
                  </td>

                  {/* Updated */}
                  <td style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {relTime(row.updated_at)}
                  </td>

                  {/* Actions */}
                  <td>
                    <div style={{ display: 'flex', gap: '0.375rem', justifyContent: 'flex-end' }}>
                      {(row.status === 'done' || row.status === 'no_match') && row.fetched_people_found > 0 && (
                        <button
                          type="button"
                          onClick={() => onViewContacts(row)}
                          aria-label={`View fetched people for ${row.domain}`}
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
                          <Users size={12} strokeWidth={2.5} />
                          {row.contacts_found > 0 ? 'View contacts' : 'View people'}
                        </button>
                      )}
                      {(row.status === 'done' || row.status === 'no_match') && (
                        <button
                          type="button"
                          disabled={fetchDisabled}
                          onClick={() => onRefetch(row.domain_id)}
                          aria-label={`Refetch contacts for ${row.domain}`}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                            fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)',
                            cursor: fetchDisabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                            whiteSpace: 'nowrap', transition: 'all 140ms', opacity: fetchDisabled ? 0.5 : 1,
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--s3)'; e.currentTarget.style.color = 'var(--s3)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)'; e.currentTarget.style.color = 'var(--oc-muted)' }}
                        >
                          <RefreshCw size={12} strokeWidth={2.5} />
                          Refetch
                        </button>
                      )}
                      {(row.status === 'pending' || row.status === 'failed') && (
                        <button
                          type="button"
                          disabled={fetchDisabled}
                          onClick={() => onFetch(row.domain_id)}
                          aria-label={`${row.status === 'failed' ? 'Retry fetching' : 'Fetch'} contacts for ${row.domain}`}
                          style={{
                            display: 'inline-flex', alignItems: 'center',
                            padding: '0.4375rem 0.75rem', minHeight: '34px', borderRadius: '0.375rem',
                            border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                            fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)',
                            cursor: fetchDisabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                            transition: 'all 140ms',
                            opacity: fetchDisabled ? 0.5 : 1,
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
