import { useState } from 'react'
import type { ActiveView } from '../../lib/navigation'
import type { CampaignStageCounts } from '../../lib/types'
import { BottomSheet } from './bottom-nav/BottomSheet'
import type { SheetItem } from './bottom-nav/BottomSheet'
import {
  IconPulse, IconBuilding, IconGlobe, IconChart, IconUsers,
  IconCheck, IconSliders, IconCog, IconWorkflow,
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

const HOME_VIEWS:     ActiveView[] = ['dashboard', 'campaigns']
const PIPELINE_VIEWS: ActiveView[] = ['s1-scraping', 's2-ai', 's3-contacts', 's4-validation']
const TOOLS_VIEWS:    ActiveView[] = ['full-pipeline']
const CONFIG_VIEWS:   ActiveView[] = ['settings', 'operations']

type OpenSheet = 'home' | 'pipeline' | 'tools' | null

interface BottomNavProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  onOpenPromptLibrary: () => void
  stageCounts?: CampaignStageCounts | null
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
  stageCounts,
}: BottomNavProps) {
  const [openSheet, setOpenSheet] = useState<OpenSheet>(null)

  function toggle(sheet: OpenSheet) {
    setOpenSheet((prev) => (prev === sheet ? null : sheet))
  }

  function navigate(view: ActiveView) {
    setActiveView(view)
    setOpenSheet(null)
  }

  // Pipeline items are rendered from the shared campaign stage-count contract.
  const pipelineItems: SheetItem[] = [
    { view: 's1-scraping',   label: 'Scraping',        Icon: IconGlobe, stageColor: 'var(--s1)', count: stageCounts?.scraping.badge ?? 0, isLive: stageCounts?.scraping.is_live ?? false },
    { view: 's2-ai',         label: 'AI Review',       Icon: IconChart, stageColor: 'var(--s2)', count: stageCounts?.ai_review.badge ?? 0, isLive: stageCounts?.ai_review.is_live ?? false },
    { view: 's3-contacts',   label: 'Contacts & Email',Icon: IconUsers, stageColor: 'var(--s3)', count: stageCounts?.contacts.badge ?? 0, isLive: stageCounts?.contacts.is_live ?? false },
    { view: 's4-validation', label: 'Validation',      Icon: IconCheck, stageColor: 'var(--s5)', count: stageCounts?.validation.badge ?? 0, isLive: stageCounts?.validation.is_live ?? false },
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
        <Tab id="pipeline" label="Pipeline" Icon={IconWorkflow} isActive={isPipelineActive} isOpen={openSheet === 'pipeline'} onClick={() => toggle('pipeline')} />
        <Tab id="tools"    label="Tools"    Icon={IconSliders}  isActive={isToolsActive}    isOpen={openSheet === 'tools'}    onClick={() => toggle('tools')} />
        <Tab id="config"   label="Config"   Icon={IconCog}      isActive={isConfigActive}   isOpen={false}                   onClick={() => navigate('settings')} />
      </nav>
    </>
  )
}
