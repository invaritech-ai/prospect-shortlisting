import { useState } from 'react'
import type { ReactNode } from 'react'
import type { CampaignRead, StatsResponse } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import { Sidebar }        from './Sidebar'
import { BottomNav }      from './BottomNav'
import { MobileHeader }   from './header/MobileHeader'
import { DesktopHeader }  from './header/DesktopHeader'
import {
  IconBuilding, IconGlobe, IconChart, IconPulse,
  IconUsers, IconTimeline, IconSliders, IconCheck, IconCog, IconHistory, IconUpload,
} from '../ui/icons'

const STAGE_COLOR: Partial<Record<ActiveView, string>> = {
  's1-scraping':   'var(--s1)',
  's2-ai':         'var(--s2)',
  's3-contacts':   'var(--s3)',
  's5-validation': 'var(--s5)',
}

const VIEW_META: Record<ActiveView, { label: string; Icon: React.FC<{ size?: number; className?: string }> }> = {
  dashboard:       { label: 'Dashboard',        Icon: IconPulse    },
  operations:      { label: 'Operations',        Icon: IconTimeline },
  campaigns:       { label: 'Campaigns',         Icon: IconBuilding },
  uploads:         { label: 'Uploads',           Icon: IconUpload   },
  settings:        { label: 'Config',            Icon: IconCog      },
  'full-pipeline': { label: 'Full Pipeline',     Icon: IconSliders  },
  's1-scraping':   { label: 'Scraping',          Icon: IconGlobe    },
  's2-ai':         { label: 'AI Review',         Icon: IconChart    },
  's3-contacts':   { label: 'Contacts & Email',  Icon: IconUsers    },
  's4-reveal':     { label: 'Retry Reveals',     Icon: IconUsers    },
  's5-validation': { label: 'Validation',        Icon: IconCheck    },
  'queue-history': { label: 'Queue History',     Icon: IconHistory  },
}

const SIDEBAR_COLLAPSED_KEY = 'ps:sidebar-collapsed'

interface AppShellProps {
  className?: string
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  activeCampaignName?: string | null
  campaigns: CampaignRead[]
  selectedCampaignId: string | null
  onSelectCampaign: (id: string) => void
  stats: StatsResponse | null
  scrapeRemainingCount?: number | null
  scrapeIsLive?: boolean
  onOpenPromptLibrary: () => void
  authEnabled?: boolean
  userDisplayName?: string | null
  onLogout?: () => void
  children: ReactNode
}

export function AppShell({
  className = '',
  activeView, setActiveView,
  activeCampaignName,
  campaigns, selectedCampaignId, onSelectCampaign,
  stats,
  scrapeRemainingCount = null,
  scrapeIsLive = false,
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

  const toggleCollapsed = () => setCollapsed((prev) => {
    const next = !prev
    try { window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next)) } catch { /* ignore */ }
    return next
  })

  const { label, Icon } = VIEW_META[activeView]
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
        stats={stats}
        scrapeRemainingCount={scrapeRemainingCount}
        scrapeIsLive={scrapeIsLive}
      />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <MobileHeader
          viewLabel={label}
          Icon={Icon}
          stageColor={stageColor}
          campaignName={activeCampaignName}
          stats={stats}
          authEnabled={authEnabled}
          onLogout={onLogout}
        />

        <DesktopHeader
          viewLabel={label}
          activeView={activeView}
          Icon={Icon}
          stageColor={stageColor}
          campaignName={activeCampaignName}
          stats={stats}
          authEnabled={authEnabled}
          userDisplayName={userDisplayName}
          onLogout={onLogout}
        />

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
        stats={stats}
        scrapeRemainingCount={scrapeRemainingCount}
        scrapeIsLive={scrapeIsLive}
      />
    </div>
  )
}
