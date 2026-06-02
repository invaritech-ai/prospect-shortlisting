import type { EmailFetchCompanyStatus } from '../../../lib/types'

const CONFIG: Record<EmailFetchCompanyStatus, { label: string; color: string; bg: string; dot?: boolean }> = {
  pending:  { label: 'Pending',   color: 'var(--oc-muted)',         bg: 'var(--oc-surface-dim)' },
  running:  { label: 'Fetching',  color: 'var(--s3)',               bg: 'var(--s3-bg)',    dot: true },
  done:     { label: 'Done',      color: 'var(--oc-success-text)',   bg: 'var(--oc-success-bg)' },
  failed:   { label: 'Failed',    color: 'var(--oc-fail-text)',      bg: 'var(--oc-fail-bg)' },
  no_match: { label: 'No match',  color: 'var(--oc-warn-text)',      bg: 'var(--oc-warn-bg)' },
}

export function ContactStatusBadge({ status }: { status: EmailFetchCompanyStatus }) {
  const cfg = CONFIG[status]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
      padding: '0.25rem 0.625rem', borderRadius: '9999px',
      fontSize: '0.75rem', fontWeight: 600,
      color: cfg.color, backgroundColor: cfg.bg, whiteSpace: 'nowrap',
    }}>
      {cfg.dot && (
        <span style={{
          width: '6px', height: '6px', borderRadius: '9999px',
          backgroundColor: cfg.color, flexShrink: 0,
          animation: 'oc-ping 1.5s cubic-bezier(0,0,0.2,1) infinite',
        }} />
      )}
      {cfg.label}
    </span>
  )
}
