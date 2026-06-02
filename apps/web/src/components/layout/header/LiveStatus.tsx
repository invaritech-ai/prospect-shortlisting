import type { CampaignStageCounts } from '../../../lib/types'
import { LiveDot } from '../../ui/LiveDot'

interface LiveStatusProps {
  stageCounts: CampaignStageCounts | null
  stageColor?: string // current view's stage color, if any
  activeView: string
}

type StageKey = 'scraping' | 'ai_review' | 'contacts' | 'validation'

const STAGE_MAP: Record<string, { key: StageKey; label: string; color: string }> = {
  's1-scraping':   { key: 'scraping',   label: 'Scraping',   color: 'var(--s1)' },
  's2-ai':         { key: 'ai_review',  label: 'AI Review',  color: 'var(--s2)' },
  's3-contacts':   { key: 'contacts',   label: 'Contacts',   color: 'var(--s3)' },
  's5-validation': { key: 'validation', label: 'Validation', color: 'var(--s5)' },
}

function liveParts(stageCounts: CampaignStageCounts, key: StageKey): string[] {
  if (key === 'scraping') {
    const counts = stageCounts.scraping
    return [
      counts.running > 0 ? `${counts.running} running` : '',
      counts.queued > 0 ? `${counts.queued} queued` : '',
    ].filter(Boolean)
  }
  if (key === 'ai_review') {
    const counts = stageCounts.ai_review
    return [
      counts.running > 0 ? `${counts.running} running` : '',
      counts.queued > 0 ? `${counts.queued} queued` : '',
    ].filter(Boolean)
  }
  if (key === 'contacts') {
    const counts = stageCounts.contacts
    return counts.running > 0 ? [`${counts.running} fetching`] : []
  }
  const counts = stageCounts.validation
  return counts.running > 0 ? [`${counts.running} validating`] : []
}

function isStageLive(stageCounts: CampaignStageCounts, key: StageKey): boolean {
  return stageCounts[key].is_live
}

export function LiveStatus({ stageCounts, stageColor: _stageColor, activeView }: LiveStatusProps) {
  if (!stageCounts) {
    return (
      <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
        Counts unavailable
      </span>
    )
  }

  // If we're on a stage view, show that stage's status specifically
  const stageInfo = STAGE_MAP[activeView]
  if (stageInfo) {
    const parts = liveParts(stageCounts, stageInfo.key)

    if (parts.length > 0) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.125rem', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <LiveDot color={stageInfo.color} size="md" />
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: stageInfo.color, whiteSpace: 'nowrap' }}>
              {parts.join(' · ')}
            </span>
          </div>
        </div>
      )
    }
  }

  // Cross-stage overview: collect active stages
  const active = [
    isStageLive(stageCounts, 'scraping') && { label: 'Scraping', color: 'var(--s1)' },
    isStageLive(stageCounts, 'ai_review') && { label: 'AI Review', color: 'var(--s2)' },
    isStageLive(stageCounts, 'contacts') && { label: 'Contacts', color: 'var(--s3)' },
    isStageLive(stageCounts, 'validation') && { label: 'Validation', color: 'var(--s5)' },
  ].filter(Boolean) as { label: string; color: string }[]

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
  const updatedAt = new Date(stageCounts.updated_at)
  const diffMin = Math.floor((Date.now() - updatedAt.getTime()) / 60_000)
  const timeStr = diffMin < 1 ? 'just now' : diffMin < 60 ? `${diffMin}m ago` : updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
      All quiet · updated {timeStr}
    </span>
  )
}
