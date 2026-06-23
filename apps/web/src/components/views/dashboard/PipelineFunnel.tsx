import type { FunnelSummary } from '../../../lib/types'

function pct(a: number, b: number): string {
  if (!b) return '—'
  return `${Math.round((a / b) * 100)}%`
}

interface FunnelStepProps {
  label: string
  value: number
  subLabel: string
  color: string
  isLast?: boolean
}

function FunnelStep({ label, value, subLabel, color, isLast = false }: FunnelStepProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontWeight: 700,
          fontSize: 'clamp(1.375rem, 3vw, 2rem)',
          letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums',
          color, lineHeight: 1,
        }}>
          {value.toLocaleString()}
        </div>
        <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-text)', marginTop: '0.25rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {label}
        </div>
        <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>
          {subLabel}
        </div>
      </div>
      {!isLast && (
        <div style={{ padding: '0 0.625rem', color: 'var(--oc-border)', fontSize: '1rem', flexShrink: 0, paddingBottom: '1.25rem' }}>
          →
        </div>
      )}
    </div>
  )
}

interface PipelineFunnelProps {
  funnel: FunnelSummary
}

export function PipelineFunnel({ funnel }: PipelineFunnelProps) {
  const conversionRate = pct(funnel.validEmails, funnel.uploaded)

  return (
    <div className="oc-panel" style={{ padding: '1.5rem' }}>
      <p className="oc-label" style={{ marginBottom: '1.25rem' }}>Pipeline Progress</p>

      <div style={{ display: 'flex', alignItems: 'flex-start', overflowX: 'auto', gap: 0 }}>
        <FunnelStep label="Uploaded"       value={funnel.uploaded}      subLabel="starting point"                             color="var(--oc-muted)" />
        <FunnelStep label="Scraped"        value={funnel.scraped}       subLabel={pct(funnel.scraped, funnel.uploaded)}        color="var(--s1)" />
        <FunnelStep label="Possible"       value={funnel.possible}      subLabel={pct(funnel.possible, funnel.uploaded)}       color="var(--s2)" />
        <FunnelStep label="Contacts Found" value={funnel.contactsFound} subLabel={`${pct(funnel.contactsFound, funnel.possible)} of Possible`} color="var(--s3)" />
        <FunnelStep label="Valid Emails"   value={funnel.validEmails}   subLabel={`${pct(funnel.validEmails, funnel.contactsFound)} delivery rate`} color="var(--s5)" isLast />
      </div>

      <div style={{ marginTop: '1.25rem', height: '0.375rem', borderRadius: '9999px', background: 'var(--oc-border)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: '9999px',
          width: conversionRate,
          background: 'linear-gradient(90deg, var(--s1), var(--s2), var(--s3), var(--s5))',
          transition: 'width 600ms ease',
        }} />
      </div>
      <p style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.5rem', textAlign: 'right' }}>
        {conversionRate} end-to-end conversion
      </p>
    </div>
  )
}
