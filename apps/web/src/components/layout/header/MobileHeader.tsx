import type { CampaignStageCounts } from '../../../lib/types'
import { LiveDot } from '../../ui/LiveDot'

interface MobileHeaderProps {
  viewLabel: string
  Icon: React.FC<{ size?: number; className?: string }>
  stageColor: string | undefined
  campaignName: string | null | undefined
  stageCounts: CampaignStageCounts | null
  authEnabled: boolean
  onLogout?: () => void
}

function isAnyActive(stageCounts: CampaignStageCounts): boolean {
  return (
    stageCounts.scraping.is_live
    || stageCounts.ai_review.is_live
    || stageCounts.contacts.is_live
    || stageCounts.validation.is_live
  )
}

export function MobileHeader({
  viewLabel, Icon, stageColor, campaignName, stageCounts, authEnabled, onLogout,
}: MobileHeaderProps) {
  const accentColor  = stageColor ?? 'var(--oc-accent)'
  const isLive       = stageCounts ? isAnyActive(stageCounts) : false

  return (
    <header className="oc-mobile-header">
      {/* Logo mark — keeps identity without text */}
      <img
        src="/prospect-console-mark.svg"
        alt="Prospect Console"
        style={{ height: '1.625rem', width: '1.625rem', borderRadius: '0.3125rem', flexShrink: 0 }}
      />

      <span className="oc-header-divider" />

      {/* View identity */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0, flex: 1 }}>
        <span style={{ color: accentColor, flexShrink: 0, display: 'flex' }}>
          <Icon size={15} />
        </span>
        <div style={{ minWidth: 0 }}>
          <span style={{
            display: 'block',
            fontFamily: 'var(--font-display)',
            fontSize: '1rem',
            color: accentColor,
            lineHeight: 1.15,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {viewLabel}
          </span>
          {campaignName && (
            <span style={{
              display: 'block', fontSize: '0.6875rem', fontWeight: 500,
              color: 'var(--oc-muted)', lineHeight: 1,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {campaignName}
            </span>
          )}
        </div>
      </div>

      {/* Live dot — only when active */}
      {isLive && (
        <span style={{ flexShrink: 0 }}>
          <LiveDot color={accentColor} size="md" />
        </span>
      )}

      {authEnabled && onLogout && (
        <button type="button" onClick={onLogout} className="oc-header-logout-btn" style={{ flexShrink: 0 }}>
          Out
        </button>
      )}
    </header>
  )
}
