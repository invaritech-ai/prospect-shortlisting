import type { ScrapeStatus } from '../../../lib/useAppData'
import { LiveDot } from '../../ui/LiveDot'

const STATUS_CONFIG: Record<ScrapeStatus, { label: string; color: string; bg: string; border: string }> = {
  pending: { label: 'Pending',  color: 'var(--oc-muted)',         bg: 'var(--oc-surface-dim)', border: 'var(--oc-border)'  },
  running: { label: 'Running',  color: 'var(--s1)',               bg: 'var(--s1-bg)',          border: 'color-mix(in srgb, var(--s1) 25%, white)' },
  done:    { label: 'Done',     color: 'var(--oc-success-text)',  bg: 'var(--oc-success-bg)',  border: 'color-mix(in srgb, var(--oc-success-text) 20%, white)' },
  failed:  { label: 'Failed',   color: 'var(--oc-fail-text)',     bg: 'var(--oc-fail-bg)',     border: 'color-mix(in srgb, var(--oc-fail-text) 20%, white)' },
}

interface ScrapeStatusBadgeProps {
  status: ScrapeStatus
}

export function ScrapeStatusBadge({ status }: ScrapeStatusBadgeProps) {
  const cfg = STATUS_CONFIG[status]

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
      borderRadius: '9999px', padding: '0.25rem 0.625rem',
      border: `1px solid ${cfg.border}`,
      background: cfg.bg,
      fontSize: '0.75rem', fontWeight: 600, color: cfg.color,
      whiteSpace: 'nowrap',
    }}>
      {status === 'running' && <LiveDot color={cfg.color} />}
      {cfg.label}
    </span>
  )
}
