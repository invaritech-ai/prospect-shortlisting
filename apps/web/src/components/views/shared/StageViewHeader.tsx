import { LiveDot } from '../../ui/LiveDot'

function fmtEta(secs: number): string {
  if (secs < 60)   return `${secs}s left`
  if (secs < 3600) return `~${Math.ceil(secs / 60)}m left`
  return `~${(secs / 3600).toFixed(1)}h left`
}

interface StatPill {
  label: string
  value: number
  color?: string
  live?: boolean
}

interface StageAction {
  label: string
  onClick: () => void
  disabled?: boolean
  variant?: 'primary' | 'secondary'
}

interface StageViewHeaderProps {
  stageNum: string          // "S1"
  stageLabel: string        // "Scraping"
  stageColor: string        // "var(--s1)"
  stageBg: string           // "var(--s1-bg)"
  stats: StatPill[]
  etaSeconds?: number | null
  primaryAction?: StageAction
  secondaryAction?: StageAction
}

export function StageViewHeader({
  stageNum, stageLabel, stageColor, stageBg,
  stats, etaSeconds,
  primaryAction, secondaryAction,
}: StageViewHeaderProps) {
  const isLive = stats.some((s) => s.live && s.value > 0)

  return (
    <div style={{
      borderRadius: '1.125rem',
      border: `1px solid color-mix(in srgb, ${stageColor} 25%, white)`,
      background: stageBg,
      padding: '1.375rem 1.5rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '1rem',
    }}>
      {/* Stage identity row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
        <div>
          {/* Stage number eyebrow */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: stageColor, flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.2em', color: stageColor }}>
              {stageNum}
            </span>
            {isLive && <LiveDot color={stageColor} size="sm" />}
          </div>

          {/* Stage name — big, Calistoga */}
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(1.5rem, 4vw, 2.25rem)', color: stageColor, margin: 0, lineHeight: 1.1, letterSpacing: '-0.02em' }}>
            {stageLabel}
          </h1>

          {/* ETA */}
          {etaSeconds != null && etaSeconds > 0 && (
            <p style={{ fontSize: '0.8125rem', color: stageColor, opacity: 0.75, margin: '0.25rem 0 0', fontWeight: 500 }}>
              {fmtEta(etaSeconds)}
            </p>
          )}
        </div>

        {/* Actions */}
        {(primaryAction || secondaryAction) && (
          <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            {secondaryAction && (
              <button
                type="button"
                onClick={secondaryAction.onClick}
                disabled={secondaryAction.disabled}
                className="oc-btn oc-btn-secondary oc-btn-sm"
              >
                {secondaryAction.label}
              </button>
            )}
            {primaryAction && (
              <button
                type="button"
                onClick={primaryAction.onClick}
                disabled={primaryAction.disabled}
                className="oc-btn oc-btn-md"
                style={{
                  backgroundColor: stageColor, color: '#fff',
                  borderColor: stageColor,
                  boxShadow: `0 2px 8px color-mix(in srgb, ${stageColor} 35%, transparent)`,
                  opacity: primaryAction.disabled ? 0.5 : 1,
                }}
              >
                {primaryAction.label}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {stats.map((stat) => (
          <div key={stat.label} style={{
            display: 'flex', alignItems: 'center', gap: '0.375rem',
            borderRadius: '9999px',
            padding: '0.3125rem 0.75rem',
            background: 'color-mix(in srgb, white 60%, transparent)',
            border: `1px solid color-mix(in srgb, ${stageColor} 20%, white)`,
          }}>
            {stat.live && stat.value > 0 && <LiveDot color={stat.color ?? stageColor} />}
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.9375rem', color: stat.color ?? stageColor, fontVariantNumeric: 'tabular-nums' }}>
              {stat.value.toLocaleString()}
            </span>
            <span style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--oc-muted)' }}>
              {stat.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
