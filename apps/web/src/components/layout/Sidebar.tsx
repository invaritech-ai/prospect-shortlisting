import { useEffect, useRef, useState } from 'react'
import type { CampaignRead } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import {
  IconBuilding,
  IconGlobe,
  IconChart,
  IconPulse,
  IconCog,
  IconUsers,
  IconTimeline,
  IconSliders,
  IconCheck,
  IconZap,
  IconChevronLeft,
  IconChevronRight,
} from '../ui/icons'

interface SidebarProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  campaigns: CampaignRead[]
  selectedCampaignId: string | null
  onSelectCampaign: (id: string) => void
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
  { value: 'operations', label: 'Operations', Icon: IconTimeline },
  { value: 'campaigns', label: 'Campaigns', Icon: IconBuilding },
  { value: 'settings', label: 'Settings', Icon: IconCog },
  { value: 'full-pipeline', label: 'Full Pipeline', Icon: IconSliders },
  { value: 's1-scraping', label: 'S1 · Scraping', stageColor: 'var(--s1)', Icon: IconGlobe },
  { value: 's2-ai', label: 'S2 · AI Decision', stageColor: 'var(--s2)', Icon: IconChart },
  { value: 's3-contacts', label: 'S3 · Contacts', stageColor: 'var(--s3)', Icon: IconUsers },
  { value: 's4-reveal', label: 'S4 · Reveal', stageColor: 'var(--s4)', Icon: IconZap },
  { value: 's5-validation', label: 'S5 · Validation', stageColor: 'var(--s5)', Icon: IconCheck },
]

export function Sidebar({
  activeView,
  setActiveView,
  campaigns,
  selectedCampaignId,
  onSelectCampaign,
  collapsed,
  onToggleCollapsed,
}: SidebarProps) {
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const activeCampaign = campaigns.find((c) => c.id === selectedCampaignId) ?? null

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [dropdownOpen])

  return (
    <aside
      className="hidden shrink-0 overflow-hidden border-r border-(--oc-border) bg-(--oc-surface-strong) md:flex md:flex-col"
      style={{
        width: collapsed ? '56px' : 'var(--oc-sidebar-w)',
        transition: 'width 220ms cubic-bezier(0.4,0,0.2,1)',
      }}
    >
      <div className="flex h-full flex-col overflow-hidden py-4">
        {/* Brand + campaign switcher */}
        <div
          className="relative mb-5 overflow-visible"
          style={{ padding: collapsed ? '0 12px' : '0 12px 0 14px' }}
          ref={dropdownRef}
        >
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setDropdownOpen((o) => !o)}
              title={collapsed ? (activeCampaign?.name ?? 'Select campaign') : undefined}
              className="shrink-0 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-(--oc-accent)"
            >
              <img
                src="/prospect-console-mark.svg"
                alt="Prospect Console"
                className="h-8 w-8 rounded-lg"
              />
            </button>

            {/* Expanded: name + campaign trigger */}
            <button
              type="button"
              onClick={() => setDropdownOpen((o) => !o)}
              className="min-w-0 flex-1 text-left overflow-hidden transition-all duration-200 focus:outline-none"
              style={{ opacity: collapsed ? 0 : 1, maxWidth: collapsed ? 0 : 200, pointerEvents: collapsed ? 'none' : 'auto' }}
            >
              <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-(--oc-muted)">Prospect</p>
              <p className="text-sm font-extrabold text-(--oc-accent-ink) leading-none">Console</p>
              <div className="mt-1 flex items-center gap-1">
                <p className="truncate text-[11px] font-semibold text-(--oc-text)">
                  {activeCampaign ? activeCampaign.name : <span className="text-(--oc-muted) font-normal">Select campaign…</span>}
                </p>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                  className="shrink-0 text-(--oc-muted)" style={{ opacity: collapsed ? 0 : 1 }}>
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
            </button>
          </div>

          {/* Dropdown */}
          {dropdownOpen && (
            <div
              className="absolute left-0 z-50 mt-2 rounded-xl border border-(--oc-border) bg-(--oc-surface) shadow-lg"
              style={{ minWidth: 200, top: '100%' }}
            >
              <div className="max-h-60 overflow-y-auto py-1">
                {campaigns.length === 0 && (
                  <p className="px-3 py-2 text-xs text-(--oc-muted)">No campaigns yet.</p>
                )}
                {campaigns.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => { onSelectCampaign(c.id); setDropdownOpen(false) }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition hover:bg-(--oc-surface-strong)"
                  >
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: c.id === selectedCampaignId ? 'var(--oc-accent)' : 'transparent', border: '1.5px solid var(--oc-border)' }}
                    />
                    <span className={`truncate ${c.id === selectedCampaignId ? 'font-semibold text-(--oc-accent-ink)' : 'text-(--oc-text)'}`}>
                      {c.name}
                    </span>
                  </button>
                ))}
              </div>
              <div className="border-t border-(--oc-border) px-3 py-2">
                <button
                  type="button"
                  onClick={() => { setActiveView('campaigns'); setDropdownOpen(false) }}
                  className="text-xs text-(--oc-muted) transition hover:text-(--oc-accent-ink)"
                >
                  Manage campaigns →
                </button>
              </div>
            </div>
          )}
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
                <Icon size={18} className="shrink-0" />
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
        <div className="mt-3 border-t border-(--oc-border) px-2 pt-3">
          <button
            type="button"
            onClick={onToggleCollapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="oc-nav-item w-full"
            style={{ justifyContent: collapsed ? 'center' : 'flex-end' }}
          >
            {collapsed ? (
              <IconChevronRight size={16} className="shrink-0" />
            ) : (
              <>
                <span className="text-xs opacity-70">Collapse</span>
                <IconChevronLeft size={16} className="shrink-0" />
              </>
            )}
          </button>
        </div>
      </div>
    </aside>
  )
}
