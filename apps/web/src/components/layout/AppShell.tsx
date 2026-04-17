import { useState } from 'react'
import type { ReactNode } from 'react'
import type { StatsResponse } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { IconBuilding, IconGlobe, IconChart, IconPulse, IconUsers, IconTimeline } from '../ui/icons'

interface AppShellProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  stats: StatsResponse | null
  onOpenPromptLibrary: () => void
  children: ReactNode
}

const VIEW_TITLES: Record<ActiveView, { label: string; Icon: React.FC<{ size?: number; className?: string }> }> = {
  dashboard: { label: 'Dashboard', Icon: IconPulse },
  'full-pipeline': { label: 'Full Pipeline', Icon: IconTimeline },
  's1-scraping': { label: 'S1 · Scraping', Icon: IconGlobe },
  's2-ai': { label: 'S2 · AI Decision', Icon: IconChart },
  's3-contacts': { label: 'S3 · Contact Fetch', Icon: IconUsers },
  's4-validation': { label: 'S4 · Validation', Icon: IconBuilding },
}

const SIDEBAR_COLLAPSED_KEY = 'ps:sidebar-collapsed'

export function AppShell({
  activeView,
  setActiveView,
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

  return (
    <div className="flex h-full overflow-hidden">
      {/* Desktop sidebar */}
      <Sidebar
        activeView={activeView}
        setActiveView={setActiveView}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
      />

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile top bar */}
        <header
          className="flex items-center gap-3 border-b border-(--oc-border) bg-(--oc-surface-strong) px-4 md:hidden"
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
          {stats && (stats.scrape.running > 0 || stats.analysis.running > 0) && (
            <span className="ml-auto relative flex h-2.5 w-2.5 shrink-0">
              <span className="oc-motion-ping absolute inline-flex h-full w-full animate-ping rounded-full bg-(--oc-accent) opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-(--oc-accent)" />
            </span>
          )}
        </header>

        {/* Scrollable content */}
        <main
          className="flex-1 overflow-y-auto overscroll-contain p-3 md:p-6"
          style={{ paddingBottom: 'calc(var(--oc-bottom-nav-h) + 16px)' }}
          id="main-content"
        >
          <div className="mx-auto max-w-7xl">
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
