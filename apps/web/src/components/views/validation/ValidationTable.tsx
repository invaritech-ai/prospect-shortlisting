import type { MockValidationRow } from '../../../lib/useAppData'
import { ValidationStatusBadge } from './ValidationStatusBadge'

function relTime(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (d < 1) return 'just now'
  if (d < 60) return `${d}m ago`
  return `${Math.floor(d / 60)}h ago`
}

function ScoreBar({ score }: { score: number }) {
  const color = score >= 8 ? 'var(--oc-success-text)' : score >= 5 ? 'var(--oc-warn-text)' : 'var(--oc-fail-text)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
      <div style={{ width: '40px', height: '4px', borderRadius: '9999px', background: 'var(--oc-border)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${score * 10}%`, backgroundColor: color, borderRadius: '9999px', transition: 'width 400ms ease' }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 700, color }}>{score}</span>
    </div>
  )
}

interface ValidationTableProps {
  rows: MockValidationRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onValidate: (id: string) => void
}

export function ValidationTable({ rows, selected, onToggleSelect, onToggleSelectAll, onValidate }: ValidationTableProps) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))

  return (
    <div className="oc-panel" style={{ overflow: 'hidden', padding: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="oc-compact-table" style={{ minWidth: '700px' }}>
          <thead>
            <tr>
              <th style={{ width: '2.5rem', paddingLeft: '1rem' }}>
                <input type="checkbox" checked={allSelected} onChange={onToggleSelectAll} style={{ accentColor: 'var(--s5)' }} />
              </th>
              <th>Contact</th>
              <th>Email</th>
              <th style={{ width: '140px' }}>Status</th>
              <th style={{ width: '90px' }}>Score</th>
              <th style={{ width: '80px' }}>Updated</th>
              <th style={{ width: '90px' }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isSelected = selected.has(row.id)
              return (
                <tr key={row.id} style={{ backgroundColor: isSelected ? 'color-mix(in srgb, var(--s5) 5%, transparent)' : undefined }}>

                  <td style={{ paddingLeft: '1rem' }}>
                    <input type="checkbox" checked={isSelected} onChange={() => onToggleSelect(row.id)} style={{ accentColor: 'var(--s5)' }} />
                  </td>

                  {/* Contact */}
                  <td>
                    <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--oc-text)' }}>{row.contactName}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.0625rem' }}>
                      {row.title} · <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem' }}>{row.domain}</span>
                    </div>
                  </td>

                  {/* Email */}
                  <td>
                    <a
                      href={`mailto:${row.email}`}
                      style={{
                        fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', fontWeight: 500,
                        color: 'var(--oc-text)', textDecoration: 'none',
                        borderBottom: '1px dashed var(--oc-border)',
                        transition: 'color 120ms, border-color 120ms',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--s5)'; e.currentTarget.style.borderBottomColor = 'var(--s5)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-text)'; e.currentTarget.style.borderBottomColor = 'var(--oc-border)' }}
                    >
                      {row.email}
                    </a>
                  </td>

                  {/* Status */}
                  <td><ValidationStatusBadge status={row.status} subStatus={row.subStatus} /></td>

                  {/* Score */}
                  <td>
                    {row.score != null
                      ? <ScoreBar score={row.score} />
                      : <span style={{ color: 'var(--oc-muted)', fontSize: '0.8125rem' }}>—</span>
                    }
                  </td>

                  {/* Updated */}
                  <td style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {relTime(row.updatedAt)}
                  </td>

                  {/* Actions */}
                  <td>
                    {(row.status === 'pending' || row.status === 'unknown') && (
                      <button
                        type="button"
                        onClick={() => onValidate(row.id)}
                        style={{
                          display: 'inline-flex', alignItems: 'center',
                          padding: '0.25rem 0.75rem', borderRadius: '0.375rem',
                          border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                          fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)',
                          cursor: 'pointer', fontFamily: 'inherit', transition: 'all 140ms',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--s5)'; e.currentTarget.style.color = 'var(--s5)' }}
                        onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)'; e.currentTarget.style.color = 'var(--oc-muted)' }}
                      >
                        Validate
                      </button>
                    )}
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
