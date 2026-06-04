import type { EmailVerificationStatus } from '../../../lib/types'

const CONFIG: Record<EmailVerificationStatus, { label: string; color: string; bg: string; dot?: boolean }> = {
  pending: { label: 'Pending', color: 'var(--oc-muted)', bg: 'var(--oc-surface-dim)' },
  checking: { label: 'Checking', color: 'var(--s5)', bg: 'var(--s5-bg)', dot: true },
  stale: { label: 'Stale', color: 'var(--oc-warn-text)', bg: 'var(--oc-warn-bg)' },
  valid: { label: 'Valid', color: 'var(--oc-success-text)', bg: 'var(--oc-success-bg)' },
  undeliverable: { label: 'Undeliverable', color: 'var(--oc-fail-text)', bg: 'var(--oc-fail-bg)' },
  catch_all: { label: 'Catch-all', color: 'var(--oc-warn-text)', bg: 'var(--oc-warn-bg)' },
  unknown: { label: 'Unknown', color: 'var(--oc-muted)', bg: 'var(--oc-surface-dim)' },
  failed: { label: 'Failed', color: 'var(--oc-fail-text)', bg: 'var(--oc-fail-bg)' },
}

interface ValidationStatusBadgeProps {
  status: EmailVerificationStatus
  subStatus?: string | null
}

export function ValidationStatusBadge({ status, subStatus }: ValidationStatusBadgeProps) {
  const cfg = CONFIG[status]
  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', gap: '0.125rem' }}>
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.3rem',
        padding: '0.25rem 0.625rem',
        borderRadius: '9999px',
        fontSize: '0.75rem',
        fontWeight: 650,
        color: cfg.color,
        backgroundColor: cfg.bg,
        whiteSpace: 'nowrap',
      }}>
        {cfg.dot && (
          <span style={{
            width: '6px',
            height: '6px',
            borderRadius: '9999px',
            backgroundColor: cfg.color,
            flexShrink: 0,
            animation: 'oc-ping 1.5s cubic-bezier(0,0,0.2,1) infinite',
          }} />
        )}
        {cfg.label}
      </span>
      {subStatus && (
        <span style={{ fontSize: '0.625rem', fontWeight: 650, color: cfg.color, paddingLeft: '0.625rem', opacity: 0.75, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {subStatus.replace(/_/g, ' ')}
        </span>
      )}
    </div>
  )
}
