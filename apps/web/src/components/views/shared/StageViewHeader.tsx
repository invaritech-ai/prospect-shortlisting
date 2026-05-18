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
}

interface StageViewHeaderProps {
  stageNum: string
  stageLabel: string
  stageColor: string
  stageBg: string
  stats: StatPill[]
  etaSeconds?: number | null
  primaryAction?: StageAction
  secondaryAction?: StageAction
  onOpenSettings?: () => void
  settingsLabel?: string
}

export function StageViewHeader({
  stageNum, stageLabel, stageColor, stageBg,
  stats, etaSeconds,
  primaryAction, secondaryAction,
  onOpenSettings, settingsLabel = 'Settings',
}: StageViewHeaderProps) {
  const isLive = stats.some((s) => s.live && s.value > 0)

  return (
    <div style={{
      borderRadius: '0.875rem',
      border: `1.5px solid color-mix(in srgb, ${stageColor} 20%, var(--oc-border))`,
      background: stageBg,
      padding: '0.875rem 1.125rem',
    }}>
      {/* Row 1: identity + actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>

        {/* Stage identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4375rem', flexShrink: 0 }}>
          <span style={{ width: '7px', height: '7px', borderRadius: '2px', backgroundColor: stageColor, flexShrink: 0 }} />
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.5625rem', fontWeight: 800,
            textTransform: 'uppercase', letterSpacing: '0.2em', color: stageColor,
          }}>
            {stageNum}
          </span>
          {isLive && <LiveDot color={stageColor} size="sm" />}
        </div>

        {/* Stage name */}
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: '1.375rem', color: stageColor,
          margin: 0, lineHeight: 1, letterSpacing: '-0.015em', flexShrink: 0,
        }}>
          {stageLabel}
        </h1>

        {/* ETA */}
        {etaSeconds != null && (
          etaSeconds > 0 ? (
            <span style={{ fontSize: '0.75rem', color: stageColor, opacity: 0.65, fontWeight: 500, flexShrink: 0 }}>
              · {fmtEta(etaSeconds)}
            </span>
          ) : (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
              fontSize: '0.6875rem', fontWeight: 700,
              color: 'var(--oc-warn-text)',
              backgroundColor: 'var(--oc-warn-bg)',
              padding: '0.1875rem 0.5rem', borderRadius: '9999px',
              border: '1px solid color-mix(in srgb, var(--oc-warn-text) 20%, var(--oc-border))',
              flexShrink: 0,
            }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '9999px', backgroundColor: 'var(--oc-warn-text)', animation: 'oc-ping 1.5s ease infinite', flexShrink: 0 }} />
              Running longer than expected
            </span>
          )
        )}

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Action buttons — uniform height */}
        <div style={{ display: 'flex', gap: '0.375rem', flexShrink: 0, alignItems: 'center' }}>
          {onOpenSettings && (
            <button
              type="button"
              onClick={onOpenSettings}
              title={settingsLabel}
              aria-label={settingsLabel}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                padding: '0 0.75rem', height: '36px',
                borderRadius: '0.5rem',
                border: `1.5px solid color-mix(in srgb, ${stageColor} 30%, var(--oc-border))`,
                background: `color-mix(in srgb, ${stageColor} 8%, white)`,
                color: stageColor, fontWeight: 600, fontSize: '0.8125rem',
                cursor: 'pointer', fontFamily: 'inherit', transition: 'all 160ms',
                whiteSpace: 'nowrap',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
              {settingsLabel}
            </button>
          )}
          {secondaryAction && (
            <button
              type="button"
              onClick={secondaryAction.onClick}
              disabled={secondaryAction.disabled}
              style={{
                display: 'inline-flex', alignItems: 'center',
                padding: '0 0.875rem', height: '36px',
                borderRadius: '0.5rem',
                border: `1.5px solid color-mix(in srgb, ${stageColor} 40%, var(--oc-border))`,
                background: 'white',
                color: stageColor, fontWeight: 600, fontSize: '0.8125rem',
                cursor: secondaryAction.disabled ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit', transition: 'all 160ms',
                opacity: secondaryAction.disabled ? 0.45 : 1,
                whiteSpace: 'nowrap',
              }}
            >
              {secondaryAction.label}
            </button>
          )}
          {primaryAction && (
            <button
              type="button"
              onClick={primaryAction.onClick}
              disabled={primaryAction.disabled}
              style={{
                display: 'inline-flex', alignItems: 'center',
                padding: '0 1rem', height: '36px',
                borderRadius: '0.5rem',
                border: 'none',
                background: stageColor,
                color: '#fff', fontWeight: 700, fontSize: '0.8125rem',
                cursor: primaryAction.disabled ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit', transition: 'all 160ms',
                opacity: primaryAction.disabled ? 0.45 : 1,
                boxShadow: `0 2px 8px color-mix(in srgb, ${stageColor} 35%, transparent)`,
                whiteSpace: 'nowrap',
              }}
            >
              {primaryAction.label}
            </button>
          )}
        </div>
      </div>

      {/* Row 2: stat pills */}
      <div style={{ display: 'flex', gap: '0.375rem', flexWrap: 'wrap', marginTop: '0.625rem' }}>
        {stats.map((stat) => (
          <div key={stat.label} style={{
            display: 'inline-flex', alignItems: 'center', gap: '0.3125rem',
            borderRadius: '9999px',
            padding: '0.25rem 0.625rem',
            background: 'color-mix(in srgb, white 65%, transparent)',
            border: `1px solid color-mix(in srgb, ${stageColor} 18%, white)`,
          }}>
            {stat.live && stat.value > 0 && <LiveDot color={stat.color ?? stageColor} />}
            <span style={{
              fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.875rem',
              color: stat.color ?? stageColor, fontVariantNumeric: 'tabular-nums',
            }}>
              {stat.value.toLocaleString()}
            </span>
            <span style={{ fontSize: '0.6875rem', fontWeight: 500, color: 'var(--oc-muted)' }}>
              {stat.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
