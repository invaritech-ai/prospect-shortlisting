import { LiveDot } from '../../ui/LiveDot'

// Maps both old mock statuses and new DB statuses to display config
const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  pending:    { label: 'Pending',  color: 'var(--oc-muted)',        bg: 'var(--oc-surface-dim)', border: 'var(--oc-border)' },
  queued:     { label: 'Queued',   color: 'var(--oc-muted)',        bg: 'var(--oc-surface-dim)', border: 'var(--oc-border)' },
  running:    { label: 'Running',  color: 'var(--s1)',              bg: 'var(--s1-bg)',          border: 'color-mix(in srgb, var(--s1) 25%, white)' },
  done:       { label: 'Done',     color: 'var(--oc-success-text)', bg: 'var(--oc-success-bg)',  border: 'color-mix(in srgb, var(--oc-success-text) 20%, white)' },
  succeeded:  { label: 'Done',     color: 'var(--oc-success-text)', bg: 'var(--oc-success-bg)',  border: 'color-mix(in srgb, var(--oc-success-text) 20%, white)' },
  failed:     { label: 'Failed',   color: 'var(--oc-fail-text)',    bg: 'var(--oc-fail-bg)',     border: 'color-mix(in srgb, var(--oc-fail-text) 20%, white)' },
}

const FALLBACK_CONFIG = { label: 'Pending', color: 'var(--oc-muted)', bg: 'var(--oc-surface-dim)', border: 'var(--oc-border)' }

interface ScrapeStatusBadgeProps {
  status: string
}

export function ScrapeStatusBadge({ status }: ScrapeStatusBadgeProps) {
  const cfg = STATUS_CONFIG[status] ?? FALLBACK_CONFIG
  const isLive = status === 'running' || status === 'queued'

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
      borderRadius: '9999px', padding: '0.25rem 0.625rem',
      border: `1px solid ${cfg.border}`,
      background: cfg.bg,
      fontSize: '0.75rem', fontWeight: 600, color: cfg.color,
      whiteSpace: 'nowrap',
    }}>
      {isLive && <LiveDot color={cfg.color} />}
      {cfg.label}
    </span>
  )
}
