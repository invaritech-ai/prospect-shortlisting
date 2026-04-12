import type { PromptRead, CompanyCounts, ContactCountsResponse } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import {
  IconBuilding,
  IconGlobe,
  IconChart,
  IconTimeline,
  IconPulse,
  IconUsers,
  IconPencil,
  IconDownload,
  IconChevronLeft,
  IconChevronRight,
} from '../ui/icons'
import { PipelineFlow } from './PipelineFlow'

interface SidebarProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  companyCounts: CompanyCounts | null
  contactCounts: ContactCountsResponse | null
  onNavigateToPipelineStage: (view: ActiveView, stageFilter?: string) => void
  selectedPrompt: PromptRead | null
  onOpenPromptLibrary: () => void
  exportUrl: string
  collapsed: boolean
  onToggleCollapsed: () => void
}

const NAV_ITEMS: Array<{
  value: ActiveView
  label: string
  Icon: React.FC<{ className?: string; size?: number }>
}> = [
  { value: 'companies', label: 'Companies', Icon: IconBuilding },
  { value: 'jobs', label: 'Scrape Jobs', Icon: IconGlobe },
  { value: 'runs', label: 'Analysis Runs', Icon: IconChart },
  { value: 'contacts', label: 'Contacts', Icon: IconUsers },
  { value: 'operations', label: 'Operations Log', Icon: IconTimeline },
  { value: 'analytics', label: 'Analytics Snapshot', Icon: IconPulse },
]


export function Sidebar({
  activeView,
  setActiveView,
  companyCounts,
  contactCounts,
  onNavigateToPipelineStage,
  selectedPrompt,
  onOpenPromptLibrary,
  exportUrl,
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
          {/* Label fades + slides out */}
          <div
            className="overflow-hidden transition-all duration-200"
            style={{
              opacity: collapsed ? 0 : 1,
              maxWidth: collapsed ? 0 : 200,
              whiteSpace: 'nowrap',
            }}
          >
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-(--oc-muted)">Prospect</p>
            <p className="text-sm font-extrabold text-[var(--oc-accent-ink)] leading-none">Console</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-0.5 overflow-hidden px-2" aria-label="Main navigation">
          {NAV_ITEMS.map(({ value, label, Icon }) => (
            <button
              key={value}
              type="button"
              onClick={() => setActiveView(value)}
              data-active={activeView === value}
              title={collapsed ? label : undefined}
              className="oc-nav-item w-full text-left"
              style={{ justifyContent: collapsed ? 'center' : undefined }}
            >
              <Icon size={18} className="flex-shrink-0" />
              <span
                className="overflow-hidden whitespace-nowrap transition-all duration-200"
                style={{ maxWidth: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}
              >
                {label}
              </span>
            </button>
          ))}
        </nav>

        {/* Bottom section */}
        <div className="mt-4 space-y-2 overflow-hidden px-2">
          {/* Prompt button */}
          {collapsed ? (
            <button
              type="button"
              onClick={onOpenPromptLibrary}
              title="Prompt Library"
              className="oc-nav-item w-full"
              style={{ justifyContent: 'center' }}
            >
              <IconPencil size={18} className="flex-shrink-0" />
            </button>
          ) : (
            <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">Active Prompt</p>
              {selectedPrompt ? (
                <>
                  <p className="mt-1.5 truncate text-xs font-semibold text-[var(--oc-accent-ink)]">
                    {selectedPrompt.name}
                  </p>
                  <span className={`mt-1.5 oc-badge ${selectedPrompt.enabled ? 'oc-badge-success' : 'oc-badge-fail'}`}>
                    {selectedPrompt.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </>
              ) : (
                <p className="mt-1.5 text-xs text-(--oc-muted)">No prompt selected</p>
              )}
              <button
                type="button"
                onClick={onOpenPromptLibrary}
                className="mt-3 flex w-full items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-[11px] font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
              >
                <IconPencil size={13} />
                Prompt Library
              </button>
            </div>
          )}

          {/* Pipeline stage navigator */}
          <PipelineFlow
            activeView={activeView}
            companyCounts={companyCounts}
            contactCounts={contactCounts}
            collapsed={collapsed}
            onNavigate={onNavigateToPipelineStage}
          />

          {/* Export */}
          <a
            href={exportUrl}
            title={collapsed ? 'Export CSV' : undefined}
            className="oc-nav-item flex w-full items-center gap-2 no-underline"
            style={{ justifyContent: collapsed ? 'center' : undefined }}
          >
            <IconDownload size={16} className="flex-shrink-0" />
            <span
              className="overflow-hidden whitespace-nowrap text-xs font-semibold transition-all duration-200"
              style={{ maxWidth: collapsed ? 0 : 200, opacity: collapsed ? 0 : 1 }}
            >
              Export CSV
            </span>
          </a>
        </div>

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
