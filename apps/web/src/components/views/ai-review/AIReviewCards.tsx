import type { AIReviewRow, AIVerdict } from '../../../lib/types'
import { VerdictBadge } from './VerdictBadge'
import { QuickLabelPicker } from './QuickLabelPicker'
import { formatRelativeTime as relTime } from '../shared/relativeTime'
import { Maximize2 } from 'lucide-react'

interface AIReviewCardsProps {
  rows: AIReviewRow[]
  selectedIds: Set<string>
  onToggleRow: (id: string) => void
  onLabelChange: (id: string, verdict: AIVerdict) => void
  onViewReasoning: (row: AIReviewRow) => void
}

export function AIReviewCards({ rows, selectedIds, onToggleRow, onLabelChange, onViewReasoning }: AIReviewCardsProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {rows.map((row) => {
        const isSelected = selectedIds.has(row.id)
        return (
          <div
            key={row.id}
            className="oc-panel"
            style={{
              padding: '1rem',
              display: 'flex', flexDirection: 'column', gap: '0.75rem',
              borderColor: isSelected ? 'var(--s2)' : undefined,
              boxShadow: isSelected ? '0 0 0 2px color-mix(in srgb, var(--s2) 20%, transparent)' : undefined,
              transition: 'border-color 160ms, box-shadow 160ms',
              cursor: 'default',
            }}
          >
            {/* Header row */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggleRow(row.id)}
                style={{ accentColor: 'var(--s2)', marginTop: '2px', flexShrink: 0 }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.9375rem',
                    fontWeight: 600, color: 'var(--oc-text)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {row.domain}
                  </span>
                  <VerdictBadge verdict={row.verdict} />
                </div>
              </div>

              {/* Confidence */}
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700,
                color: row.confidence >= 80 ? 'var(--s2)' : row.confidence >= 50 ? 'var(--oc-warn-text)' : 'var(--oc-fail-text)',
                flexShrink: 0,
              }}>
                {row.confidence}%
              </span>
            </div>

            {/* Reasoning — truncated + explicit expand button */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
              <p style={{
                margin: 0, flex: 1, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.5,
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>
                {row.reasoning}
              </p>
              <button
                type="button"
                onClick={() => onViewReasoning(row)}
                title="View full reasoning"
                style={{
                  flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '26px', height: '26px', borderRadius: '0.375rem',
                  border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                  cursor: 'pointer', color: 'var(--oc-muted)',
                }}
              >
                <Maximize2 size={12} strokeWidth={2.5} />
              </button>
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>
                {row.pagesReviewed} pages · {relTime(row.updatedAt)}
              </span>
              <QuickLabelPicker
                current={row.verdict}
                onChange={(v) => onLabelChange(row.id, v)}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
