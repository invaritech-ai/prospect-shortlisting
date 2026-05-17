import { useState } from 'react'
import type { ReactNode } from 'react'
import type { CampaignRead, StatsResponse } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { IconBuilding, IconGlobe, IconChart, IconPulse, IconUsers, IconTimeline, IconSliders, IconCheck, IconCog, IconHistory } from '../ui/icons'

/** Maps each stage view to its CSS variable so --current-stage is set globally */
const STAGE_COLOR: Partial<Record<string, string>> = {
  's1-scraping':   'var(--s1)',
  's2-ai':         'var(--s2)',
  's3-contacts':   'var(--s3)',
  's5-validation': 'var(--s5)',
}

interface AppShellProps {
  className?: string
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  activeCampaignName?: string | null
  campaigns: CampaignRead[]
  selectedCampaignId: string | null
  onSelectCampaign: (id: string) => void
  stats: StatsResponse | null
  onOpenPromptLibrary: () => void
  authEnabled?: boolean
  userDisplayName?: string | null
  onLogout?: () => void
  children: ReactNode
}

function sliceQueueBusy(s: { running: number; queued: number; stuck_count?: number } | undefined): boolean {
  if (!s) return false
  return s.running > 0 || s.queued > 0 || (s.stuck_count ?? 0) > 0
}

function hasPipelineActivity(stats: StatsResponse): boolean {
  return (
    sliceQueueBusy(stats.scrape)
    || sliceQueueBusy(stats.analysis)
    || sliceQueueBusy(stats.contact_fetch)
    || sliceQueueBusy(stats.validation)
  )
}

function DesktopLiveSummary({ stats }: { stats: StatsResponse | null }) {
  if (!stats) {
    return <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Loading activity…</span>
  }
  const { scrape, analysis, contact_fetch: cf, validation: v } = stats
  const rows: { key: string; label: string; color: string; s: typeof scrape }[] = []
  if (sliceQueueBusy(scrape)) rows.push({ key: 's1', label: 'S1', color: 'var(--s1)', s: scrape })
  if (sliceQueueBusy(analysis)) rows.push({ key: 's2', label: 'S2', color: 'var(--s2)', s: analysis })
  if (sliceQueueBusy(cf)) rows.push({ key: 's3', label: 'S3', color: 'var(--s3)', s: cf! })
  if (sliceQueueBusy(v)) rows.push({ key: 's5', label: 'S5', color: 'var(--s5)', s: v! })
  if (rows.length === 0) {
    return (
      <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        Updated {new Date(stats.as_of).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.125rem', minWidth: 0, maxHeight: '4rem', overflowY: 'auto' }}>
      {rows.map((r) => (
        <span key={r.key} style={{ fontSize: '0.75rem', fontWeight: 500, color: r.color, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {r.label} {r.s.running} run · {r.s.queued} q{r.s.stuck_count ? ` · ${r.s.stuck_count} stuck` : ''}
        </span>
      ))}
    </div>
  )
}

const VIEW_TITLES: Record<ActiveView, { label: string; Icon: React.FC<{ size?: number; className?: string }> }> = {
  dashboard:       { label: 'Dashboard',             Icon: IconPulse },
  operations:      { label: 'Operations',             Icon: IconTimeline },
  campaigns:       { label: 'Campaigns',              Icon: IconBuilding },
  settings:        { label: 'Settings',               Icon: IconCog },
  'full-pipeline': { label: 'Full Pipeline',          Icon: IconSliders },
  's1-scraping':   { label: 'Scraping',               Icon: IconGlobe },
  's2-ai':         { label: 'AI Decision',            Icon: IconChart },
  's3-contacts':   { label: 'Contacts & Email',       Icon: IconUsers },
  's4-reveal':     { label: 'Retry Reveals',          Icon: IconUsers },
  's5-validation': { label: 'Validation',             Icon: IconCheck },
  'queue-history': { label: 'Queue History',          Icon: IconHistory },
}

const SIDEBAR_COLLAPSED_KEY = 'ps:sidebar-collapsed'

export function AppShell({
  className = '',
  activeView,
  setActiveView,
  activeCampaignName,
  campaigns,
  selectedCampaignId,
  onSelectCampaign,
  stats,
  onOpenPromptLibrary,
  authEnabled = false,
  userDisplayName = null,
  onLogout,
  children,
}: AppShellProps) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true' }
    catch { return false }
  })

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev
      try { window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next)) } catch { /* ignore */ }
      return next
    })
  }

  const { label, Icon } = VIEW_TITLES[activeView]
  const activity = stats && hasPipelineActivity(stats)
  const stageColor = STAGE_COLOR[activeView]

  return (
    <div
      className={`flex h-full min-h-0 flex-1 overflow-hidden ${className}`.trim()}
      style={{ '--current-stage': stageColor ?? '' } as React.CSSProperties}
    >
      <Sidebar
        activeView={activeView}
        setActiveView={setActiveView}
        campaigns={campaigns}
        selectedCampaignId={selectedCampaignId}
        onSelectCampaign={onSelectCampaign}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
      />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <header className="oc-mobile-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
            <img src="/prospect-console-mark.svg" alt="Prospect Console" style={{ height: '1.75rem', width: '1.75rem', flexShrink: 0, borderRadius: '0.375rem' }} />
            <div style={{ minWidth: 0 }}>
              <p style={{ fontSize: '0.625rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--oc-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Prospect</p>
              <p style={{ fontSize: '0.6875rem', fontWeight: 800, color: 'var(--oc-accent-ink)', lineHeight: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>Console</p>
            </div>
          </div>
          <span className="oc-header-divider" />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', minWidth: 0, marginLeft: '0.125rem' }}>
            <Icon size={16} className={stageColor ? 'oc-icon-stage' : 'oc-icon-accent'} />
            <div style={{ minWidth: 0 }}>
              <span style={{ display: 'block', fontSize: '0.875rem', fontWeight: 700, color: 'var(--oc-accent-ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
              <span style={{ display: 'block', fontSize: '0.625rem', fontWeight: 500, color: 'var(--oc-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                Campaign: {activeCampaignName ?? 'none selected'}
              </span>
            </div>
          </div>
          {activity && (
            <span className="oc-live-dot" style={{ marginLeft: 'auto' }}>
              <span className="oc-live-dot-ring oc-motion-ping" />
              <span className="oc-live-dot-core" />
            </span>
          )}
          {authEnabled && onLogout ? (
            <button type="button" onClick={onLogout} className="oc-header-logout-btn" style={{ marginLeft: '0.25rem' }}>
              Logout
            </button>
          ) : null}
        </header>

        {/* Desktop header */}
        <header className="oc-desktop-header">
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
              <Icon size={18} className={stageColor ? 'oc-icon-stage' : 'oc-icon-accent'} />
              <span style={{ fontSize: '0.875rem', fontWeight: 700, color: stageColor ? `var(--current-stage)` : 'var(--oc-accent-ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
            </div>
            <p style={{ fontSize: '0.625rem', fontWeight: 500, color: 'var(--oc-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              Campaign: {activeCampaignName ?? 'none selected'}
            </p>
          </div>
          <span className="oc-header-divider" />
          <div style={{ minWidth: 0, flex: 1 }}>
            <DesktopLiveSummary stats={stats} />
          </div>
          {authEnabled && userDisplayName ? (
            <span className="oc-header-user-chip">
              <IconUsers size={12} />
              {userDisplayName}
            </span>
          ) : null}
          {authEnabled && onLogout ? (
            <button type="button" onClick={onLogout} className="oc-header-logout-btn">
              Logout
            </button>
          ) : null}
          {activity && (
            <span className="oc-live-dot">
              <span className="oc-live-dot-ring oc-motion-ping" />
              <span className="oc-live-dot-core" />
            </span>
          )}
        </header>

        {/* Scrollable content */}
        <main className="oc-content-scroll" id="main-content">
          <div className="flex min-h-0 w-full flex-1 flex-col">
            {children}
          </div>
        </main>
      </div>

      <BottomNav
        activeView={activeView}
        setActiveView={setActiveView}
        onOpenPromptLibrary={onOpenPromptLibrary}
      />
    </div>
  )
}
