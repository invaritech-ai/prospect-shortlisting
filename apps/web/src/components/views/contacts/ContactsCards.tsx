import type { EmailFetchCompanyRow } from '../../../lib/types'
import { ContactStatusBadge } from './ContactStatusBadge'
import { formatRelativeTime as relTime } from '../shared/relativeTime'
import { RefreshCw } from 'lucide-react'

interface ContactsCardsProps {
  rows: EmailFetchCompanyRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onFetch: (id: string) => void
  onRefetch: (id: string) => void
  onViewContacts: (row: EmailFetchCompanyRow) => void
  fetchDisabled?: boolean
}

export function ContactsCards({ rows, selected, onToggleSelect, onFetch, onRefetch, onViewContacts, fetchDisabled = false }: ContactsCardsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {rows.map((row) => {
        const isSelected = selected.has(row.domain_id)
        return (
          <div
            key={row.domain_id}
            className="oc-panel"
            style={{
              padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem',
              borderColor: isSelected ? 'var(--s3)' : undefined,
              boxShadow: isSelected ? '0 0 0 2px color-mix(in srgb, var(--s3) 20%, transparent)' : undefined,
              transition: 'border-color 160ms, box-shadow 160ms',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(row.domain_id)} style={{ accentColor: 'var(--s3)', flexShrink: 0 }} />
              <a
                href={row.normalized_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  flex: 1, fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 600,
                  color: 'var(--oc-text)', textDecoration: 'none',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                {row.domain} ↗
              </a>
              <ContactStatusBadge status={row.status} />
            </div>

            {/* Stats row */}
            {(row.contacts_found > 0 || row.fetched_people_found > 0) && (
              <div style={{ display: 'flex', gap: '1.25rem' }}>
                {row.fetched_people_found > 0 && (
                  <div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.375rem', fontWeight: 800, color: 'var(--oc-muted)', lineHeight: 1 }}>
                      {row.fetched_people_found}
                    </div>
                    <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', fontWeight: 500, marginTop: '0.125rem' }}>fetched</div>
                  </div>
                )}
                <div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.375rem', fontWeight: 800, color: 'var(--s3)', lineHeight: 1 }}>
                    {row.contacts_found}
                  </div>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', fontWeight: 500, marginTop: '0.125rem' }}>contacts</div>
                </div>
                {row.emails_found > 0 && (
                  <div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.375rem', fontWeight: 800, color: 'var(--oc-success-text)', lineHeight: 1 }}>
                      {row.emails_found}
                    </div>
                    <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', fontWeight: 500, marginTop: '0.125rem' }}>emails</div>
                  </div>
                )}
              </div>
            )}

            {/* Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>{relTime(row.updated_at)}</span>
              {(row.status === 'done' || row.status === 'no_match') && (
                <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {row.fetched_people_found > 0 && (
                    <button
                      type="button"
                      onClick={() => onViewContacts(row)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                        padding: '0.4375rem 0.875rem', borderRadius: '0.5rem',
                        border: '1.5px solid var(--s3)', background: 'var(--s3-bg)',
                        fontSize: '0.8125rem', fontWeight: 700, color: 'var(--s3)',
                        cursor: 'pointer', fontFamily: 'inherit', minHeight: '44px',
                      }}
                    >
                      {row.contacts_found > 0 ? `View ${row.contacts_found} contacts` : 'View fetched people'}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={fetchDisabled}
                    onClick={() => onRefetch(row.domain_id)}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                      padding: '0.4375rem 0.875rem', borderRadius: '0.5rem',
                      border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                      fontSize: '0.8125rem', fontWeight: 600, color: 'var(--oc-muted)',
                      cursor: fetchDisabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit', minHeight: '44px',
                      opacity: fetchDisabled ? 0.5 : 1,
                    }}
                  >
                    <RefreshCw size={12} strokeWidth={2.5} />
                    Refetch
                  </button>
                </div>
              )}
              {(row.status === 'pending' || row.status === 'failed') && (
                <button
                  type="button"
                  disabled={fetchDisabled}
                  onClick={() => onFetch(row.domain_id)}
                  style={{
                    display: 'inline-flex', alignItems: 'center',
                    padding: '0.4375rem 0.875rem', borderRadius: '0.5rem',
                    border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                    fontSize: '0.8125rem', fontWeight: 600, color: 'var(--oc-muted)',
                    cursor: fetchDisabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit', minHeight: '44px',
                    opacity: fetchDisabled ? 0.5 : 1,
                  }}
                >
                  {row.status === 'failed' ? 'Retry' : 'Fetch contacts'}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
