import type { MockAIRow, AIVerdict } from '../../../lib/useAppData'
import { VerdictBadge } from './VerdictBadge'
import { QuickLabelPicker } from './QuickLabelPicker'

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ago`
}

interface AIReviewTableProps {
  rows: MockAIRow[]
  selectedIds: Set<string>
  onToggleRow: (id: string) => void
  onToggleAll: () => void
  onLabelChange: (id: string, verdict: AIVerdict) => void
  onViewReasoning: (row: MockAIRow) => void
  hasActiveFilter?: boolean
  onClearFilter?: () => void
}

export function AIReviewTable({ rows, selectedIds, onToggleRow, onToggleAll, onLabelChange, onViewReasoning, hasActiveFilter, onClearFilter }: AIReviewTableProps) {
  const allSelected = rows.length > 0 && rows.every((r) => selectedIds.has(r.id))

  return (
    <div className="oc-panel" style={{ overflow: 'hidden', padding: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="oc-compact-table" style={{ minWidth: '780px' }}>
          <thead>
            <tr>
              <th style={{ width: '2.5rem', paddingLeft: '1rem' }}>
                <input type="checkbox" checked={allSelected} onChange={onToggleAll} style={{ accentColor: 'var(--s2)' }} />
              </th>
              <th>Domain</th>
              <th style={{ width: '100px' }}>Verdict</th>
              <th style={{ width: '76px' }}>Confidence</th>
              <th style={{ width: '48px', textAlign: 'center' }}>Pages</th>
              <th>Reasoning</th>
              <th style={{ width: '80px' }}>Reviewed</th>
              <th style={{ width: '200px' }}>Override</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: '3rem 1.5rem', textAlign: 'center' }}>
                  <div style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginBottom: '0.625rem' }}>
                    {hasActiveFilter ? 'No companies match this filter.' : 'No companies have been classified yet.'}
                  </div>
                  {hasActiveFilter && onClearFilter && (
                    <button type="button" onClick={onClearFilter}
                      style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--s2)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: '2px' }}>
                      Clear filter
                    </button>
                  )}
                  {!hasActiveFilter && (
                    <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>Run S1 Scraping first, then AI classification will queue automatically.</span>
                  )}
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const isSelected = selectedIds.has(row.id)
              return (
                <tr key={row.id} style={{ backgroundColor: isSelected ? 'color-mix(in srgb, var(--s2) 5%, transparent)' : undefined }}>

                  {/* Checkbox */}
                  <td style={{ paddingLeft: '1rem' }}>
                    <input type="checkbox" checked={isSelected} onChange={() => onToggleRow(row.id)} style={{ accentColor: 'var(--s2)' }} />
                  </td>

                  {/* Domain — external link */}
                  <td>
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', fontWeight: 600,
                        color: 'var(--oc-text)', textDecoration: 'none',
                        borderBottom: '1px dashed var(--oc-border)', transition: 'color 120ms, border-color 120ms',
                        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--s2)'; e.currentTarget.style.borderBottomColor = 'var(--s2)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-text)'; e.currentTarget.style.borderBottomColor = 'var(--oc-border)' }}
                    >
                      {row.domain}
                      <svg style={{ opacity: 0.4, flexShrink: 0 }} width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                    </a>
                  </td>

                  {/* Verdict */}
                  <td><VerdictBadge verdict={row.verdict} /></td>

                  {/* Confidence */}
                  <td>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: '0.875rem', fontWeight: 700,
                      color: row.confidence >= 80 ? 'var(--s2)' : row.confidence >= 50 ? 'var(--oc-warn-text)' : 'var(--oc-fail-text)',
                    }}>
                      {row.confidence}%
                    </span>
                  </td>

                  {/* Pages */}
                  <td style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', color: 'var(--oc-muted)', fontWeight: 500 }}>
                    {row.pagesReviewed}
                  </td>

                  {/* Reasoning — passive truncated text + explicit expand button */}
                  <td style={{ maxWidth: '260px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', minWidth: 0 }}>
                      <span style={{
                        fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.4,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
                      }}>
                        {row.reasoning}
                      </span>
                      <button
                        type="button"
                        onClick={() => onViewReasoning(row)}
                        title="View full reasoning"
                        aria-label={`View full AI reasoning for ${row.domain}`}
                        style={{
                          flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: '30px', height: '30px', borderRadius: '0.375rem',
                          border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                          cursor: 'pointer', color: 'var(--oc-muted)', transition: 'all 140ms',
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--s2)'; e.currentTarget.style.color = 'var(--s2)' }}
                        onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)'; e.currentTarget.style.color = 'var(--oc-muted)' }}
                      >
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
                        </svg>
                      </button>
                    </div>
                  </td>

                  {/* Time */}
                  <td style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {relTime(row.updatedAt)}
                  </td>

                  {/* Override */}
                  <td>
                    <QuickLabelPicker current={row.verdict} onChange={(v) => onLabelChange(row.id, v)} />
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
