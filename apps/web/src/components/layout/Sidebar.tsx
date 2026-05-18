import type { CampaignRead, CompanyCounts, StatsResponse } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import { MOCK_COMPANY_COUNTS, MOCK_STATS, MOCK_CAMPAIGNS } from '../../lib/useAppData'
import { CampaignPicker } from './sidebar/CampaignPicker'
import { NavSection }    from './sidebar/NavSection'
import { StageNavItem }  from './sidebar/StageNavItem'
import {
  IconPulse, IconBuilding, IconGlobe, IconChart, IconUsers, IconCheck,
  IconSliders, IconCog, IconChevronLeft, IconChevronRight,
} from '../ui/icons'

interface SidebarProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  campaigns: CampaignRead[]
  selectedCampaignId: string | null
  onSelectCampaign: (id: string) => void
  collapsed: boolean
  onToggleCollapsed: () => void
  companyCounts?: CompanyCounts | null
  stats?: StatsResponse | null
}

export function Sidebar({
  activeView, setActiveView,
  campaigns: rawCampaigns,
  selectedCampaignId, onSelectCampaign,
  collapsed, onToggleCollapsed,
  companyCounts: rawCounts,
  stats: rawStats,
}: SidebarProps) {
  // Fall back to mock data while backend isn't wired
  const campaigns = rawCampaigns.length ? rawCampaigns : MOCK_CAMPAIGNS
  const counts    = rawCounts ?? MOCK_COMPANY_COUNTS
  const stats     = rawStats  ?? MOCK_STATS

  const selectedId = selectedCampaignId ?? (campaigns[0]?.id ?? null)

  const stageCounts = {
    s1: counts.uploaded,
    s2: counts.unknown,
    s3: counts.contact_ready,
    s5: Math.max(0, (stats.validation?.total ?? 0) - (stats.validation?.succeeded ?? 0) - (stats.validation?.failed ?? 0)),
  }

  const stageLive = {
    s1: stats.scrape.running > 0,
    s2: (stats.analysis?.running ?? 0) > 0,
    s3: (stats.contact_fetch?.running ?? 0) > 0,
    s5: (stats.validation?.running ?? 0) > 0,
  }

  function nav(view: ActiveView) { return () => setActiveView(view) }
  function isActive(view: ActiveView) { return activeView === view }

  return (
    <aside
      className="oc-sidebar"
      style={{ width: collapsed ? '56px' : 'var(--oc-sidebar-w)', transition: 'width 240ms cubic-bezier(0.4,0,0.2,1)' }}
    >
      <div style={{ display: 'flex', height: '100%', flexDirection: 'column', overflow: 'hidden', paddingTop: '1rem', paddingBottom: '0.75rem' }}>

        {/* Brand */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          padding: collapsed ? '0 0.875rem' : '0 1rem',
          marginBottom: '0.875rem',
          overflow: 'hidden',
        }}>
          <img src="/prospect-console-mark.svg" alt="" style={{ width: '1.5rem', height: '1.5rem', borderRadius: '0.375rem', flexShrink: 0 }} />
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: '1rem', color: 'var(--oc-text)',
            whiteSpace: 'nowrap', transition: 'max-width 200ms, opacity 200ms',
            maxWidth: collapsed ? 0 : 160, opacity: collapsed ? 0 : 1, overflow: 'hidden',
          }}>
            Prospect
          </span>
        </div>

        {/* Campaign picker */}
        <CampaignPicker
          campaigns={campaigns}
          selectedId={selectedId}
          onSelect={onSelectCampaign}
          onManage={nav('campaigns')}
          collapsed={collapsed}
        />

        {/* Scrollable nav */}
        <nav style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '0 0.5rem', marginTop: '0.5rem' }} aria-label="Main navigation">

          <NavSection label="Overview" collapsed={collapsed}>
            <button type="button" onClick={nav('dashboard')} title={collapsed ? 'Dashboard' : undefined}
              className="oc-nav-item" data-active={isActive('dashboard') ? 'true' : 'false'}
              style={{ '--item-accent': 'var(--oc-accent)', justifyContent: collapsed ? 'center' : undefined } as React.CSSProperties}>
              <IconPulse size={16} className="oc-icon-shrink" />
              <span style={{ overflow: 'hidden', whiteSpace: 'nowrap', transition: 'max-width 200ms, opacity 200ms', maxWidth: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}>Dashboard</span>
            </button>
            <button type="button" onClick={nav('campaigns')} title={collapsed ? 'Campaigns' : undefined}
              className="oc-nav-item" data-active={isActive('campaigns') ? 'true' : 'false'}
              style={{ '--item-accent': 'var(--oc-accent)', justifyContent: collapsed ? 'center' : undefined } as React.CSSProperties}>
              <IconBuilding size={16} className="oc-icon-shrink" />
              <span style={{ overflow: 'hidden', whiteSpace: 'nowrap', transition: 'max-width 200ms, opacity 200ms', maxWidth: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}>Campaigns</span>
            </button>
          </NavSection>

          <NavSection label="Pipeline" collapsed={collapsed}>
            <StageNavItem view="s1-scraping"   label="Scraping"         stageColor="var(--s1)" Icon={IconGlobe}  isActive={isActive('s1-scraping')}   count={stageCounts.s1} isLive={stageLive.s1} collapsed={collapsed} onClick={nav('s1-scraping')} />
            <StageNavItem view="s2-ai"         label="AI Review"        stageColor="var(--s2)" Icon={IconChart}  isActive={isActive('s2-ai')}         count={stageCounts.s2} isLive={stageLive.s2} collapsed={collapsed} onClick={nav('s2-ai')} />
            <StageNavItem view="s3-contacts"   label="Contacts & Email" stageColor="var(--s3)" Icon={IconUsers}  isActive={isActive('s3-contacts')}   count={stageCounts.s3} isLive={stageLive.s3} collapsed={collapsed} onClick={nav('s3-contacts')} />
            <StageNavItem view="s5-validation" label="Validation"       stageColor="var(--s5)" Icon={IconCheck}  isActive={isActive('s5-validation')} count={stageCounts.s5} isLive={stageLive.s5} collapsed={collapsed} onClick={nav('s5-validation')} />
          </NavSection>

          <NavSection label="Tools" collapsed={collapsed}>
            <button type="button" onClick={nav('full-pipeline')} title={collapsed ? 'Full Pipeline' : undefined}
              className="oc-nav-item" data-active={isActive('full-pipeline') ? 'true' : 'false'}
              style={{ '--item-accent': 'var(--oc-accent)', justifyContent: collapsed ? 'center' : undefined } as React.CSSProperties}>
              <IconSliders size={16} className="oc-icon-shrink" />
              <span style={{ overflow: 'hidden', whiteSpace: 'nowrap', transition: 'max-width 200ms, opacity 200ms', maxWidth: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}>Full Pipeline</span>
            </button>
          </NavSection>

        </nav>

        {/* Config + collapse toggle at bottom */}
        <div style={{ padding: '0 0.5rem', borderTop: '1px solid var(--oc-border)', paddingTop: '0.625rem' }}>
          <button type="button" onClick={nav('settings')} title={collapsed ? 'Config' : undefined}
            className="oc-nav-item" data-active={isActive('settings') ? 'true' : 'false'}
            style={{ '--item-accent': 'var(--oc-accent)', justifyContent: collapsed ? 'center' : undefined } as React.CSSProperties}>
            <IconCog size={16} className="oc-icon-shrink" />
            <span style={{ overflow: 'hidden', whiteSpace: 'nowrap', transition: 'max-width 200ms, opacity 200ms', maxWidth: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}>Config</span>
          </button>

          <button type="button" onClick={onToggleCollapsed} title={collapsed ? 'Expand' : 'Collapse'}
            className="oc-nav-item" style={{ justifyContent: collapsed ? 'center' : 'flex-end', marginTop: '0.125rem' }}>
            {collapsed
              ? <IconChevronRight size={14} className="oc-icon-shrink" />
              : <><span style={{ fontSize: '0.75rem', opacity: 0.5 }}>Collapse</span><IconChevronLeft size={14} className="oc-icon-shrink" /></>
            }
          </button>
        </div>

      </div>
    </aside>
  )
}
