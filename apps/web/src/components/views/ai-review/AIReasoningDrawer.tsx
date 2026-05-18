import type { MockAIRow } from '../../../lib/useAppData'
import { Drawer } from '../../ui/Drawer'
import { VerdictBadge } from './VerdictBadge'

interface AIReasoningDrawerProps {
  row: MockAIRow | null
  onClose: () => void
}

export function AIReasoningDrawer({ row, onClose }: AIReasoningDrawerProps) {
  if (!row) return null

  const confidenceColor = row.confidence >= 80 ? 'var(--s2)' : row.confidence >= 50 ? 'var(--oc-warn-text)' : 'var(--oc-fail-text)'

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title={row.domain}
      subtitle="S2 · AI Analysis"
      accentColor="var(--s2)"
    >
      {/* Verdict + confidence hero block */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '1rem',
        padding: '1.125rem 1.25rem',
        borderRadius: '0.875rem',
        backgroundColor: 'var(--s2-bg)',
        border: '1.5px solid color-mix(in srgb, var(--s2) 20%, var(--oc-border))',
        marginBottom: '1.5rem',
      }}>
        <VerdictBadge verdict={row.verdict} size="md" />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.375rem', marginLeft: 'auto' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '2rem', fontWeight: 900, color: confidenceColor, lineHeight: 1 }}>
            {row.confidence}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700, color: confidenceColor, alignSelf: 'flex-end', lineHeight: 1.4 }}>%</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', alignSelf: 'flex-end', lineHeight: 1.6, marginLeft: '0.25rem' }}>confidence</span>
        </div>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', color: 'var(--oc-muted)', alignSelf: 'flex-end', marginLeft: 'auto' }}>
          {row.pagesReviewed} pages
        </span>
      </div>

      {/* Reasoning */}
      <div style={{ marginBottom: '1.5rem' }}>
        <p style={{ fontSize: '0.625rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.18em', color: 'var(--oc-muted)', marginBottom: '0.625rem' }}>AI Reasoning</p>
        <p style={{
          fontSize: '0.9375rem', color: 'var(--oc-text)', lineHeight: 1.7, margin: 0,
          padding: '1rem 1.125rem',
          backgroundColor: 'var(--oc-surface)', borderRadius: '0.75rem',
          border: '1px solid var(--oc-border)',
        }}>
          {row.reasoning}
        </p>
      </div>

      {/* Domain link */}
      <div style={{
        padding: '0.875rem 1rem', borderRadius: '0.75rem',
        border: '1px solid var(--oc-border)', background: 'var(--oc-surface)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Company site</span>
        <a href={row.url} target="_blank" rel="noopener noreferrer"
          style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: 'var(--s2)', textDecoration: 'none', fontWeight: 600 }}>
          {row.domain} ↗
        </a>
      </div>
    </Drawer>
  )
}
