import type { IntegrationHealthItem } from '../../../lib/types'

const SERVICE_META: Record<string, { initials: string; colorVar: string }> = {
  openrouter: { initials: 'OR', colorVar: 'var(--oc-accent)' },
  apollo:     { initials: 'AP', colorVar: 'var(--s3)' },
  snov:       { initials: 'SN', colorVar: 'var(--s3)' },
  zerobounce: { initials: 'ZB', colorVar: 'var(--s5)' },
}

function formatCredits(credits: number | null, message: string): string {
  if (message) return message
  if (credits === null) return 'Connected'
  if (credits >= 1_000_000) return `${(credits / 1_000_000).toFixed(1)}M credits`
  if (credits >= 1_000) return `${(credits / 1_000).toFixed(1)}k credits`
  return `${credits.toLocaleString()} credits`
}

interface ServicesHealthProps {
  services: IntegrationHealthItem[]
  isLoading: boolean
  onOpenSettings: () => void
}

export function ServicesHealth({ services, isLoading, onOpenSettings }: ServicesHealthProps) {
  return (
    <section>
      <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Services</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
        {isLoading && !services.length
          ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 0.875rem', borderRadius: '0.75rem', background: 'var(--oc-surface-dim)' }}>
                <div className="oc-skeleton" style={{ width: '2rem', height: '2rem', borderRadius: '0.5rem', flexShrink: 0 }} />
                <div className="oc-skeleton" style={{ width: '40%', height: '0.75rem' }} />
                <div className="oc-skeleton" style={{ width: '20%', height: '0.75rem', marginLeft: 'auto' }} />
              </div>
            ))
          : services.map((svc) => {
              const meta = SERVICE_META[svc.provider] ?? { initials: svc.provider.slice(0, 2).toUpperCase(), colorVar: 'var(--oc-muted)' }
              return (
                <div key={svc.provider} style={{
                  display: 'flex', alignItems: 'center', gap: '0.75rem',
                  padding: '0.75rem 0.875rem', borderRadius: '0.75rem',
                  background: 'var(--oc-surface)', border: '1px solid var(--oc-border)',
                }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    width: '2rem', height: '2rem', borderRadius: '0.5rem', flexShrink: 0,
                    background: `color-mix(in srgb, ${meta.colorVar} 12%, white)`,
                    fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 700,
                    color: meta.colorVar,
                  }}>
                    {meta.initials}
                  </div>
                  <span style={{ flex: 1, fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)' }}>
                    {svc.label}
                  </span>
                  <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', flexShrink: 0 }}>
                    {svc.connected
                      ? formatCredits(svc.credits_remaining, svc.message)
                      : <button type="button" onClick={onOpenSettings} style={{ fontSize: '0.8125rem', color: 'var(--oc-fail-text)', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}>Not configured →</button>
                    }
                  </span>
                  <div style={{
                    width: '0.5rem', height: '0.5rem', borderRadius: '9999px', flexShrink: 0,
                    backgroundColor: svc.connected ? 'var(--oc-success-text)' : 'var(--oc-border)',
                  }} />
                </div>
              )
            })}
      </div>
    </section>
  )
}
