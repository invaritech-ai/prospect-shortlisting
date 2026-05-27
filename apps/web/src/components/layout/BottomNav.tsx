import { useState } from 'react'
import type { ActiveView } from '../../lib/navigation'
import type { CompanyCounts, StatsResponse } from '../../lib/types'
import { MOCK_COMPANY_COUNTS, MOCK_STATS } from '../../lib/useAppData'
import { BottomSheet } from './bottom-nav/BottomSheet'
import type { SheetItem } from './bottom-nav/BottomSheet'
import {
  IconPulse, IconBuilding, IconGlobe, IconChart, IconUsers,
  IconCheck, IconSliders, IconCog,
} from '../ui/icons'

// Tab 1 — Home: Dashboard + Campaigns
const HOME_ITEMS: SheetItem[] = [
  { view: 'dashboard', label: 'Dashboard', Icon: IconPulse },
  { view: 'campaigns', label: 'Campaigns', Icon: IconBuilding },
]

// Tab 3 — Tools (extended as screens are added)
const TOOLS_ITEMS: SheetItem[] = [
  { view: 'full-pipeline', label: 'Full Pipeline', Icon: IconSliders },
]

// Icon for "Pipeline" tab — four small squares representing stages
function IconPipeline({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2"  y="3"  width="5" height="5" rx="1.5" />
      <rect x="9"  y="3"  width="5" height="5" rx="1.5" />
      <rect x="16" y="3"  width="6" height="5" rx="1.5" />
      <rect x="2"  y="16" width="20" height="5" rx="1.5" />
      <line x1="4.5"  y1="8"  x2="4.5"  y2="12" />
      <line x1="11.5" y1="8"  x2="11.5" y2="12" />
      <line x1="19"   y1="8"  x2="19"   y2="12" />
      <line x1="4.5"  y1="12" x2="19"   y2="12" />
      <line x1="12"   y1="12" x2="12"   y2="16" />
    </svg>
  )
}

const HOME_VIEWS:     ActiveView[] = ['dashboard', 'campaigns']
const PIPELINE_VIEWS: ActiveView[] = ['s1-scraping', 's2-ai', 's3-contacts', 's5-validation']
const TOOLS_VIEWS:    ActiveView[] = ['full-pipeline']
const CONFIG_VIEWS:   ActiveView[] = ['settings', 'operations', 'queue-history']

type OpenSheet = 'home' | 'pipeline' | 'tools' | null

interface BottomNavProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  onOpenPromptLibrary: () => void
  companyCounts?: CompanyCounts | null
  stats?: StatsResponse | null
  scrapeRemainingCount?: number | null
  scrapeIsLive?: boolean
}

interface TabProps {
  id: string
  label: string
  Icon: React.FC<{ size?: number }>
  isActive: boolean
  isOpen: boolean
  onClick: () => void
}

function Tab({ label, Icon, isActive, isOpen, onClick }: TabProps) {
  const lit = isActive || isOpen
  return (
    <button
      type="button"
      onClick={onClick}
      className="oc-bottom-nav-item"
      data-active={lit ? 'true' : 'false'}
      style={{ flex: 1 }}
    >
      <Icon size={22} />
      <span>{label}</span>
      {lit && <span className="oc-bottom-nav-pip" />}
    </button>
  )
}

export function BottomNav({
  activeView, setActiveView,
  companyCounts: rawCounts,
  stats: rawStats,
  scrapeRemainingCount,
  scrapeIsLive,
}: BottomNavProps) {
  const counts = rawCounts ?? MOCK_COMPANY_COUNTS
  const stats  = rawStats  ?? MOCK_STATS

  const [openSheet, setOpenSheet] = useState<OpenSheet>(null)

  function toggle(sheet: OpenSheet) {
    setOpenSheet((prev) => (prev === sheet ? null : sheet))
  }

  function navigate(view: ActiveView) {
    setActiveView(view)
    setOpenSheet(null)
  }

  // Pipeline items get live counts + dots from mock/real data
  const pipelineItems: SheetItem[] = [
    { view: 's1-scraping',   label: 'Scraping',        Icon: IconGlobe, stageColor: 'var(--s1)', count: scrapeRemainingCount ?? counts.uploaded, isLive: scrapeIsLive ?? (stats.scrape.running > 0 || stats.scrape.queued > 0) },
    { view: 's2-ai',         label: 'AI Review',       Icon: IconChart, stageColor: 'var(--s2)', count: (stats.analysis?.running ?? 0) + (stats.analysis?.queued ?? 0) > 0 ? (stats.analysis?.running ?? 0) + (stats.analysis?.queued ?? 0) : counts.unknown,        isLive: (stats.analysis?.running ?? 0) > 0 },
    { view: 's3-contacts',   label: 'Contacts & Email',Icon: IconUsers, stageColor: 'var(--s3)', count: counts.contact_ready,  isLive: (stats.contact_fetch?.running ?? 0) > 0 },
    { view: 's5-validation', label: 'Validation',      Icon: IconCheck, stageColor: 'var(--s5)',
      count: Math.max(0, (stats.validation?.total ?? 0) - (stats.validation?.succeeded ?? 0) - (stats.validation?.failed ?? 0)),
      isLive: (stats.validation?.running ?? 0) > 0 },
  ]

  const isHomeActive     = HOME_VIEWS.includes(activeView)
  const isPipelineActive = PIPELINE_VIEWS.includes(activeView)
  const isToolsActive    = TOOLS_VIEWS.includes(activeView)
  const isConfigActive   = CONFIG_VIEWS.includes(activeView)

  return (
    <>
      {/* Pull-up sheets */}
      {openSheet === 'home' && (
        <BottomSheet items={HOME_ITEMS} activeView={activeView} onNavigate={navigate} onClose={() => setOpenSheet(null)} />
      )}
      {openSheet === 'pipeline' && (
        <BottomSheet items={pipelineItems} activeView={activeView} onNavigate={navigate} onClose={() => setOpenSheet(null)} />
      )}
      {openSheet === 'tools' && (
        <BottomSheet items={TOOLS_ITEMS} activeView={activeView} onNavigate={navigate} onClose={() => setOpenSheet(null)} />
      )}

      {/* Bottom bar — 4 tabs */}
      <nav className="oc-bottom-nav" aria-label="Mobile navigation">
        <Tab id="home"     label="Home"     Icon={IconPulse}    isActive={isHomeActive}     isOpen={openSheet === 'home'}     onClick={() => toggle('home')} />
        <Tab id="pipeline" label="Pipeline" Icon={IconPipeline} isActive={isPipelineActive} isOpen={openSheet === 'pipeline'} onClick={() => toggle('pipeline')} />
        <Tab id="tools"    label="Tools"    Icon={IconSliders}  isActive={isToolsActive}    isOpen={openSheet === 'tools'}    onClick={() => toggle('tools')} />
        <Tab id="config"   label="Config"   Icon={IconCog}      isActive={isConfigActive}   isOpen={false}                   onClick={() => navigate('settings')} />
      </nav>
    </>
  )
}
