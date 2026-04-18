import type { ActiveView } from '../../lib/navigation'
import {
  IconBuilding,
  IconGlobe,
  IconChart,
  IconPulse,
  IconUsers,
  IconTimeline,
  IconChevronLeft,
  IconChevronRight,
} from '../ui/icons'

interface SidebarProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  activeCampaignName?: string | null
  collapsed: boolean
  onToggleCollapsed: () => void
}

const NAV_ITEMS: Array<{
  value: ActiveView
  label: string
  stageColor?: string
  Icon: React.FC<{ className?: string; size?: number }>
}> = [
  { value: 'dashboard', label: 'Dashboard', Icon: IconPulse },
  { value: 'campaigns', label: 'Campaigns', Icon: IconBuilding },
  { value: 'full-pipeline', label: 'Full Pipeline', Icon: IconTimeline },
  { value: 's1-scraping', label: 'S1 · Scraping', stageColor: 'var(--s1)', Icon: IconGlobe },
  { value: 's2-ai', label: 'S2 · AI Decision', stageColor: 'var(--s2)', Icon: IconChart },
  { value: 's3-contacts', label: 'S3 · Contacts', stageColor: 'var(--s3)', Icon: IconUsers },
  { value: 's4-validation', label: 'S4 · Validation', stageColor: 'var(--s4)', Icon: IconBuilding },
]

export function Sidebar({
  activeView,
  setActiveView,
  activeCampaignName,
  collapsed,
  onToggleCollapsed,
}: SidebarProps) {
  return (
    <aside
      className="hidden md:flex flex-col flex-shrink-0 overflow-hidden border-r border-[var(--oc-border)] bg-[var(--oc-surface-strong)]"
      style={{
        width: collapsed ? '56px' : 'var(--oc-sidebar-w)',
        transition: 'width 220ms cubic-bezier(0.4,0,0.2,1)',
      }}
    >
      <div className="flex h-full flex-col overflow-hidden py-4">
        {/* Brand */}
        <div
          className="mb-5 flex items-center gap-2.5 overflow-hidden"
          style={{ padding: collapsed ? '0 12px' : '0 12px 0 14px' }}
        >
          <img
            src="/prospect-console-mark.svg"
            alt="Prospect Console"
            className="h-8 w-8 flex-shrink-0 rounded-lg"
          />
          <div
            className="overflow-hidden transition-all duration-200"
            style={{
              opacity: collapsed ? 0 : 1,
              maxWidth: collapsed ? 0 : 200,
              whiteSpace: 'nowrap',
            }}
          >
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-(--oc-muted)">Prospect</p>
            <p className="text-sm font-extrabold text-(--oc-accent-ink) leading-none">Console</p>
            {activeCampaignName ? (
              <p className="mt-1 truncate text-[11px] font-medium text-(--oc-muted)">
                Campaign: <span className="font-semibold text-(--oc-text)">{activeCampaignName}</span>
              </p>
            ) : (
              <p className="mt-1 truncate text-[11px] text-(--oc-muted)">Campaign: none</p>
            )}
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 overflow-hidden px-2" aria-label="Main navigation">
          {NAV_ITEMS.map(({ value, label, stageColor, Icon }) => {
            const isActive = activeView === value
            return (
              <button
                key={value}
                type="button"
                onClick={() => setActiveView(value)}
                title={collapsed ? label : undefined}
                className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? 'font-bold'
                    : 'text-(--oc-muted) hover:bg-(--oc-surface) hover:text-(--oc-text)'
                }`}
                style={
                  isActive
                    ? {
                        backgroundColor: stageColor ? `${stageColor}22` : 'var(--oc-accent-soft)',
                        color: stageColor ?? 'var(--oc-accent-ink)',
                        justifyContent: collapsed ? 'center' : undefined,
                      }
                    : { justifyContent: collapsed ? 'center' : undefined }
                }
              >
                <Icon size={18} className="flex-shrink-0" />
                <span
                  className="overflow-hidden whitespace-nowrap transition-all duration-200"
                  style={{ maxWidth: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}
                >
                  {label}
                </span>
              </button>
            )
          })}
        </nav>

        {/* Collapse toggle */}
        <div className="mt-3 border-t border-[var(--oc-border)] px-2 pt-3">
          <button
            type="button"
            onClick={onToggleCollapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="oc-nav-item w-full"
            style={{ justifyContent: collapsed ? 'center' : 'flex-end' }}
          >
            {collapsed ? (
              <IconChevronRight size={16} className="flex-shrink-0" />
            ) : (
              <>
                <span className="text-xs opacity-70">Collapse</span>
                <IconChevronLeft size={16} className="flex-shrink-0" />
              </>
            )}
          </button>
        </div>
      </div>
    </aside>
  )
}
