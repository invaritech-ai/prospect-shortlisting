import type { StatsResponse } from '../../../lib/types'
import { LiveStatus } from './LiveStatus'
import { IconUsers } from '../../ui/icons'

interface DesktopHeaderProps {
  viewLabel: string
  activeView: string
  Icon: React.FC<{ size?: number; className?: string }>
  stageColor: string | undefined
  campaignName: string | null | undefined
  stats: StatsResponse | null
  authEnabled: boolean
  userDisplayName?: string | null
  onLogout?: () => void
}

export function DesktopHeader({
  viewLabel, activeView, Icon, stageColor, campaignName,
  stats, authEnabled, userDisplayName, onLogout,
}: DesktopHeaderProps) {
  const accentColor = stageColor ?? 'var(--oc-accent)'

  return (
    <header className="oc-desktop-header">

      {/* Left — view identity */}
      <div style={{ minWidth: 0, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ color: accentColor, flexShrink: 0, display: 'flex' }}>
            <Icon size={16} />
          </span>
          <span style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.125rem',
            color: accentColor,
            lineHeight: 1,
            whiteSpace: 'nowrap',
          }}>
            {viewLabel}
          </span>
        </div>
        {campaignName && (
          <p style={{
            margin: '0.2rem 0 0 1.5rem',
            fontSize: '0.75rem', fontWeight: 500,
            color: 'var(--oc-muted)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            maxWidth: '180px',
          }}>
            {campaignName}
          </p>
        )}
      </div>

      <span className="oc-header-divider" />

      {/* Centre — live status (flex-1 so it fills remaining space) */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <LiveStatus stats={stats} stageColor={stageColor} activeView={activeView} />
      </div>

      {/* Right — user + logout */}
      {authEnabled && userDisplayName && (
        <span className="oc-header-user-chip">
          <IconUsers size={12} />
          {userDisplayName}
        </span>
      )}
      {authEnabled && onLogout && (
        <button type="button" onClick={onLogout} className="oc-header-logout-btn">
          Logout
        </button>
      )}

    </header>
  )
}
