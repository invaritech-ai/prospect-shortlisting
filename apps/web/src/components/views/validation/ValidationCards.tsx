import type { EmailVerificationContactRow } from '../../../lib/types'
import { ValidationStatusBadge } from './ValidationStatusBadge'

function contactName(row: EmailVerificationContactRow): string {
  return `${row.first_name} ${row.last_name}`.trim() || 'Unknown contact'
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never verified'
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

interface ValidationCardsProps {
  rows: EmailVerificationContactRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onValidate: (id: string) => void
  validateDisabled?: boolean
}

export function ValidationCards({
  rows,
  selected,
  onToggleSelect,
  onValidate,
  validateDisabled = false,
}: ValidationCardsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {rows.map((row) => {
        const isSelected = selected.has(row.contact_id)
        return (
          <div
            key={row.contact_id}
            className="oc-panel"
            style={{
              padding: '0.875rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
              borderRadius: '0.5rem',
              borderColor: isSelected ? 'var(--s5)' : undefined,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleSelect(row.contact_id)}
                style={{ accentColor: 'var(--s5)', flexShrink: 0, marginTop: '2px' }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--oc-text)' }}>{contactName(row)}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.0625rem' }}>{row.title || 'No title'}</div>
              </div>
              <ValidationStatusBadge status={row.status} />
            </div>

            <div style={{ display: 'grid', gap: '0.25rem' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>{row.domain}</span>
              <a
                href={`mailto:${row.selected_email}`}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  color: 'var(--s5)',
                  textDecoration: 'none',
                  overflowWrap: 'anywhere',
                }}
              >
                {row.selected_email}
              </a>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>{formatDate(row.verified_at)}</span>
              {row.action_label && (
                <button
                  type="button"
                  onClick={() => onValidate(row.contact_id)}
                  disabled={validateDisabled}
                  className="oc-btn oc-btn-secondary oc-btn-sm"
                  style={{ minHeight: '38px', opacity: validateDisabled ? 0.45 : 1 }}
                >
                  {row.action_label}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
