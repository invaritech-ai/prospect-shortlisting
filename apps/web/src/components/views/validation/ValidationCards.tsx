import type { MockValidationRow } from '../../../lib/useAppData'
import { ValidationStatusBadge } from './ValidationStatusBadge'

function relTime(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (d < 1) return 'just now'
  if (d < 60) return `${d}m ago`
  return `${Math.floor(d / 60)}h ago`
}

interface ValidationCardsProps {
  rows: MockValidationRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onValidate: (id: string) => void
}

export function ValidationCards({ rows, selected, onToggleSelect, onValidate }: ValidationCardsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {rows.map((row) => {
        const isSelected = selected.has(row.id)
        const scoreColor = row.score != null ? (row.score >= 8 ? 'var(--oc-success-text)' : row.score >= 5 ? 'var(--oc-warn-text)' : 'var(--oc-fail-text)') : 'var(--oc-muted)'

        return (
          <div
            key={row.id}
            className="oc-panel"
            style={{
              padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem',
              borderColor: isSelected ? 'var(--s5)' : undefined,
              boxShadow: isSelected ? '0 0 0 2px color-mix(in srgb, var(--s5) 20%, transparent)' : undefined,
              transition: 'border-color 160ms, box-shadow 160ms',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
              <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(row.id)} style={{ accentColor: 'var(--s5)', flexShrink: 0, marginTop: '2px' }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--oc-text)' }}>{row.contactName}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.0625rem' }}>{row.title} · {row.domain}</div>
              </div>
              <ValidationStatusBadge status={row.status} subStatus={row.subStatus} />
            </div>

            {/* Email */}
            <a
              href={`mailto:${row.email}`}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.875rem', fontWeight: 500,
                color: 'var(--s5)', textDecoration: 'none',
              }}
            >
              {row.email}
            </a>

            {/* Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                {row.score != null && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', fontWeight: 700, color: scoreColor }}>
                    {row.score}/10
                  </span>
                )}
                <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>{relTime(row.updatedAt)}</span>
              </div>
              {(row.status === 'pending' || row.status === 'unknown') && (
                <button
                  type="button"
                  onClick={() => onValidate(row.id)}
                  style={{
                    display: 'inline-flex', alignItems: 'center',
                    padding: '0.4375rem 0.875rem', borderRadius: '0.5rem',
                    border: '1.5px solid var(--s5)', background: 'var(--s5-bg)',
                    fontSize: '0.8125rem', fontWeight: 600, color: 'var(--s5)',
                    cursor: 'pointer', fontFamily: 'inherit', minHeight: '44px',
                  }}
                >
                  Validate
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
