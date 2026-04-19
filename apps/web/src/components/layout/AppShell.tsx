import { useState } from 'react'
import type { ReactNode } from 'react'
import type { StatsResponse } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { IconBuilding, IconGlobe, IconChart, IconPulse, IconUsers, IconTimeline } from '../ui/icons'

interface AppShellProps {
  className?: string
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  activeCampaignName?: string | null
  stats: StatsResponse | null
  onOpenPromptLibrary: () => void
  children: ReactNode
}

function hasPipelineActivity(stats: StatsResponse): boolean {
  return (
    stats.scrape.running > 0
    || stats.scrape.queued > 0
    || stats.analysis.running > 0
    || stats.analysis.queued > 0
    || (stats.contact_fetch?.running ?? 0) > 0
    || (stats.contact_fetch?.queued ?? 0) > 0
    || (stats.validation?.running ?? 0) > 0
    || (stats.validation?.queued ?? 0) > 0
  )
}

/** One-line summary for the desktop top bar (stays visible above scrolling content). */
function DesktopLiveSummary({ stats }: { stats: StatsResponse | null }) {
  if (!stats) {
    return <span className="truncate text-xs text-(--oc-muted)">Loading activity…</span>
  }
  const parts: string[] = []
  const { scrape, analysis, contact_fetch: cf, validation: v } = stats
  if (scrape.running || scrape.queued) {
    parts.push(`S1 ${scrape.running} running · ${scrape.queued} queued`)
  }
  if (analysis.running || analysis.queued) {
    parts.push(`S2 ${analysis.running} running · ${analysis.queued} queued`)
  }
  if ((cf?.running ?? 0) > 0 || (cf?.queued ?? 0) > 0) {
    parts.push(`S3 ${cf?.running ?? 0} running · ${cf?.queued ?? 0} queued`)
  }
  if ((v?.running ?? 0) > 0 || (v?.queued ?? 0) > 0) {
    parts.push(`S4 ${v?.running ?? 0} running · ${v?.queued ?? 0} queued`)
  }
  if (parts.length === 0) {
    return (
      <span className="truncate text-xs text-(--oc-muted)">
        Updated {new Date(stats.as_of).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
    )
  }
  return <span className="truncate text-xs font-medium text-(--oc-text)">{parts.join(' · ')}</span>
}

const VIEW_TITLES: Record<ActiveView, { label: string; Icon: React.FC<{ size?: number; className?: string }> }> = {
  dashboard: { label: 'Dashboard', Icon: IconPulse },
  campaigns: { label: 'Campaigns', Icon: IconBuilding },
  'full-pipeline': { label: 'Full Pipeline', Icon: IconTimeline },
  's1-scraping': { label: 'S1 · Scraping', Icon: IconGlobe },
  's2-ai': { label: 'S2 · AI Decision', Icon: IconChart },
  's3-contacts': { label: 'S3 · Contact Fetch', Icon: IconUsers },
  's4-validation': { label: 'S4 · Validation', Icon: IconBuilding },
}

const SIDEBAR_COLLAPSED_KEY = 'ps:sidebar-collapsed'

export function AppShell({
  className = '',
  activeView,
  setActiveView,
  activeCampaignName,
  stats,
  onOpenPromptLibrary,
  children,
}: AppShellProps) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
    } catch {
      return false
    }
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

  return (
    <div className={`flex h-full min-h-0 flex-1 overflow-hidden ${className}`.trim()}>
      {/* Desktop sidebar */}
      <Sidebar
        activeView={activeView}
        setActiveView={setActiveView}
        activeCampaignName={activeCampaignName}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
      />

      {/* Main area — column header(s) stay fixed; only <main> scrolls */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* Mobile top bar */}
        <header
          className="flex shrink-0 items-center gap-3 border-b border-(--oc-border) bg-(--oc-surface-strong) px-4 md:hidden"
          style={{ height: '52px' }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <img
              src="/prospect-console-mark.svg"
              alt="Prospect Console"
              className="h-7 w-7 shrink-0 rounded-md"
            />
            <div className="min-w-0">
              <p className="truncate text-[10px] font-bold uppercase tracking-[0.16em] text-(--oc-muted)">Prospect</p>
              <p className="truncate text-[11px] font-extrabold text-(--oc-accent-ink) leading-none">Console</p>
            </div>
          </div>
          <span className="h-5 w-px bg-(--oc-border)" />
          <div className="flex items-center gap-1.5 min-w-0 ml-0.5">
            <Icon size={16} className="text-(--oc-accent) shrink-0" />
            <span className="text-sm font-bold text-(--oc-accent-ink) truncate">{label}</span>
          </div>
          {activity && (
            <span className="ml-auto relative flex h-2.5 w-2.5 shrink-0">
              <span className="oc-motion-ping absolute inline-flex h-full w-full animate-ping rounded-full bg-(--oc-accent) opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-(--oc-accent)" />
            </span>
          )}
        </header>

        {/* Desktop top bar — outside scroll region so title + live stats stay visible */}
        <header
          className="hidden shrink-0 items-center gap-4 border-b border-(--oc-border) bg-(--oc-surface-strong)/95 px-6 py-2.5 backdrop-blur-sm md:flex"
          style={{ minHeight: '52px' }}
        >
          <div className="flex min-w-0 items-center gap-2">
            <Icon size={18} className="shrink-0 text-(--oc-accent)" />
            <span className="truncate text-sm font-bold text-(--oc-accent-ink)">{label}</span>
          </div>
          <span className="h-5 w-px shrink-0 bg-(--oc-border)" />
          <div className="min-w-0 flex-1">
            <DesktopLiveSummary stats={stats} />
          </div>
          {activity && (
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="oc-motion-ping absolute inline-flex h-full w-full animate-ping rounded-full bg-(--oc-accent) opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-(--oc-accent)" />
            </span>
          )}
        </header>

        {/* Scrollable content */}
        <main
          className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain p-3 md:px-6 md:pb-6 md:pt-3"
          style={{ paddingBottom: 'calc(var(--oc-bottom-nav-h) + 16px)' }}
          id="main-content"
        >
          <div className="mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col">
            {children}
          </div>
        </main>
      </div>

      {/* Mobile bottom nav */}
      <BottomNav
        activeView={activeView}
        setActiveView={setActiveView}
        onOpenPromptLibrary={onOpenPromptLibrary}
      />
    </div>
  )
}
