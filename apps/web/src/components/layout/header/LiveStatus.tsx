import type { StatsResponse } from '../../../lib/types'
import { MOCK_STATS } from '../../../lib/useAppData'
import { LiveDot } from '../../ui/LiveDot'

interface LiveStatusProps {
  stats: StatsResponse | null
  stageColor?: string // current view's stage color, if any
  activeView: string
}

const STAGE_MAP: Record<string, { key: keyof StatsResponse; label: string; color: string }> = {
  's1-scraping':   { key: 'scrape',         label: 'Scraping',   color: 'var(--s1)' },
  's2-ai':         { key: 'analysis',        label: 'AI Review',  color: 'var(--s2)' },
  's3-contacts':   { key: 'contact_fetch',   label: 'Contacts',   color: 'var(--s3)' },
  's5-validation': { key: 'validation',      label: 'Validation', color: 'var(--s5)' },
}

function fmtEta(secs: number | null): string | null {
  if (!secs || secs < 30) return null
  if (secs < 3600) return `~${Math.ceil(secs / 60)}m left`
  return `~${Math.ceil(secs / 3600)}h left`
}

export function LiveStatus({ stats: rawStats, stageColor: _stageColor, activeView }: LiveStatusProps) {
  const stats = rawStats ?? MOCK_STATS

  // If we're on a stage view, show that stage's status specifically
  const stageInfo = STAGE_MAP[activeView]
  if (stageInfo) {
    const s = stats[stageInfo.key] as typeof stats.scrape | undefined
    if (s && (s.running > 0 || s.queued > 0)) {
      const parts: string[] = []
      if (s.running > 0) parts.push(`${s.running} running`)
      if (s.queued > 0)  parts.push(`${s.queued} queued`)
      if ((s.stuck_count ?? 0) > 0) parts.push(`${s.stuck_count} stuck`)
      const eta = fmtEta(s.eta_seconds ?? null)

      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.125rem', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <LiveDot color={stageInfo.color} size="md" />
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: stageInfo.color, whiteSpace: 'nowrap' }}>
              {parts.join(' · ')}
            </span>
          </div>
          {eta && (
            <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', paddingLeft: '1.125rem' }}>
              {eta}
            </span>
          )}
        </div>
      )
    }
  }

  // Cross-stage overview: collect active stages
  const active = [
    stats.scrape.running > 0           && { label: 'Scraping',   running: stats.scrape.running,         color: 'var(--s1)' },
    (stats.analysis?.running ?? 0) > 0 && { label: 'AI Review',  running: stats.analysis?.running ?? 0, color: 'var(--s2)' },
    (stats.contact_fetch?.running ?? 0) > 0 && { label: 'Contacts', running: stats.contact_fetch?.running ?? 0, color: 'var(--s3)' },
    (stats.validation?.running ?? 0) > 0 && { label: 'Validation', running: stats.validation?.running ?? 0, color: 'var(--s5)' },
  ].filter(Boolean) as { label: string; running: number; color: string }[]

  if (active.length > 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
        <LiveDot color="var(--oc-accent)" size="md" />
        <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--oc-text)', whiteSpace: 'nowrap' }}>
          {active.map((a, i) => (
            <span key={a.label}>
              {i > 0 && <span style={{ color: 'var(--oc-muted)' }}> · </span>}
              <span style={{ color: a.color }}>{a.label}</span>
            </span>
          ))}
          {' '}running
        </span>
      </div>
    )
  }

  // All quiet
  const updatedAt = new Date(stats.as_of)
  const diffMin = Math.floor((Date.now() - updatedAt.getTime()) / 60_000)
  const timeStr = diffMin < 1 ? 'just now' : diffMin < 60 ? `${diffMin}m ago` : updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
      All quiet · updated {timeStr}
    </span>
  )
}
