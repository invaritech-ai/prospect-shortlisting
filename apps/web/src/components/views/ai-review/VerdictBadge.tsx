import type { AIVerdict } from '../../../lib/types'

const VERDICT_CONFIG: Record<AIVerdict, { label: string; color: string; bg: string }> = {
  Unclassified: { label: 'Unclassified', color: 'var(--oc-muted)', bg: 'var(--oc-bg)' },
  Possible: { label: 'Possible', color: 'var(--s2-text)', bg: 'var(--s2-bg)' },
  Unknown:  { label: 'Unknown',  color: 'var(--oc-warn-text)', bg: 'var(--oc-warn-bg)' },
  Crap:     { label: 'Crap',     color: 'var(--oc-fail-text)', bg: 'var(--oc-fail-bg)' },
}

interface VerdictBadgeProps {
  verdict: AIVerdict
  size?: 'sm' | 'md'
}

export function VerdictBadge({ verdict, size = 'md' }: VerdictBadgeProps) {
  const cfg = VERDICT_CONFIG[verdict]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
      fontFamily: 'var(--font-body)', fontWeight: 600,
      fontSize: size === 'sm' ? '0.6875rem' : '0.75rem',
      padding: size === 'sm' ? '0.125rem 0.5rem' : '0.25rem 0.625rem',
      borderRadius: '9999px',
      color: cfg.color, backgroundColor: cfg.bg,
      whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  )
}

export function VerdictDot({ verdict }: { verdict: AIVerdict }) {
  const colors: Record<AIVerdict, string> = {
    Unclassified: 'var(--oc-muted)',
    Possible: 'var(--s2)',
    Unknown:  'var(--oc-warn-text)',
    Crap:     'var(--oc-fail-text)',
  }
  return (
    <span style={{
      display: 'inline-block', width: '8px', height: '8px',
      borderRadius: '9999px', backgroundColor: colors[verdict], flexShrink: 0,
    }} />
  )
}
