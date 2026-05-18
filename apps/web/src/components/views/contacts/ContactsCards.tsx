import type { MockContactRow } from '../../../lib/useAppData'
import { ContactStatusBadge } from './ContactStatusBadge'

function relTime(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (d < 1) return 'just now'
  if (d < 60) return `${d}m ago`
  return `${Math.floor(d / 60)}h ago`
}

interface ContactsCardsProps {
  rows: MockContactRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onFetch: (id: string) => void
  onViewContacts: (row: MockContactRow) => void
}

export function ContactsCards({ rows, selected, onToggleSelect, onFetch, onViewContacts }: ContactsCardsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {rows.map((row) => {
        const isSelected = selected.has(row.id)
        return (
          <div
            key={row.id}
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
              <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(row.id)} style={{ accentColor: 'var(--s3)', flexShrink: 0 }} />
              <a
                href={row.url}
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
            {row.contactsFound > 0 && (
              <div style={{ display: 'flex', gap: '1.25rem' }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.375rem', fontWeight: 800, color: 'var(--s3)', lineHeight: 1 }}>
                    {row.contactsFound}
                  </div>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', fontWeight: 500, marginTop: '0.125rem' }}>contacts</div>
                </div>
                {row.emailsFound > 0 && (
                  <div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.375rem', fontWeight: 800, color: 'var(--oc-success-text)', lineHeight: 1 }}>
                      {row.emailsFound}
                    </div>
                    <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', fontWeight: 500, marginTop: '0.125rem' }}>emails</div>
                  </div>
                )}
              </div>
            )}

            {/* Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>{relTime(row.updatedAt)}</span>
              {row.status === 'done' && row.contactsFound > 0 && (
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
                  View {row.contactsFound} contacts
                </button>
              )}
              {(row.status === 'pending' || row.status === 'failed') && (
                <button
                  type="button"
                  onClick={() => onFetch(row.id)}
                  style={{
                    display: 'inline-flex', alignItems: 'center',
                    padding: '0.4375rem 0.875rem', borderRadius: '0.5rem',
                    border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                    fontSize: '0.8125rem', fontWeight: 600, color: 'var(--oc-muted)',
                    cursor: 'pointer', fontFamily: 'inherit', minHeight: '44px',
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
