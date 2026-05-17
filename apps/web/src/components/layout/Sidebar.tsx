import { useEffect, useRef, useState } from 'react'
import type { CampaignRead } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'
import {
  IconBuilding, IconGlobe, IconChart, IconPulse, IconCog,
  IconUsers, IconHistory, IconTimeline, IconSliders, IconCheck,
  IconZap, IconChevronLeft, IconChevronRight,
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
  { value: 'dashboard',      label: 'Dashboard',             Icon: IconPulse },
  { value: 'operations',     label: 'Operations',            Icon: IconTimeline },
  { value: 'campaigns',      label: 'Campaigns',             Icon: IconBuilding },
  { value: 'settings',       label: 'Settings',              Icon: IconCog },
  { value: 'full-pipeline',  label: 'Full Pipeline',         Icon: IconSliders },
  { value: 's1-scraping',    label: 'S1 · Scraping',         stageColor: 'var(--s1)', Icon: IconGlobe },
  { value: 's2-ai',          label: 'S2 · AI Decision',      stageColor: 'var(--s2)', Icon: IconChart },
  { value: 's3-contacts',    label: 'S3 · Contacts & Emails',stageColor: 'var(--s3)', Icon: IconUsers },
  { value: 's4-reveal',      label: 'S4 · Retry Reveals',    stageColor: 'var(--s4)', Icon: IconZap },
  { value: 's5-validation',  label: 'S5 · Validation',       stageColor: 'var(--s5)', Icon: IconCheck },
  { value: 'queue-history',  label: 'Queue History',         Icon: IconHistory },
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
      className="oc-sidebar"
      style={{
        width: collapsed ? '56px' : 'var(--oc-sidebar-w)',
        transition: 'width 220ms cubic-bezier(0.4,0,0.2,1)',
      }}
    >
      <div style={{ display: 'flex', height: '100%', flexDirection: 'column', overflow: 'hidden', padding: '1rem 0' }}>
        {/* Brand + campaign switcher */}
        <div
          style={{ position: 'relative', marginBottom: '1.25rem', overflow: 'visible', padding: collapsed ? '0 12px' : '0 12px 0 14px' }}
          ref={dropdownRef}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
            <button
              type="button"
              onClick={() => setDropdownOpen((o) => !o)}
              title={collapsed ? (activeCampaign?.name ?? 'Select campaign') : undefined}
              style={{ flexShrink: 0, borderRadius: '0.5rem', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
            >
              <img src="/prospect-console-mark.svg" alt="Prospect Console" style={{ height: '2rem', width: '2rem', borderRadius: '0.5rem' }} />
            </button>

            <button
              type="button"
              onClick={() => setDropdownOpen((o) => !o)}
              style={{
                minWidth: 0, flex: 1, textAlign: 'left', overflow: 'hidden', background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                transition: 'opacity 200ms, max-width 200ms',
                opacity: collapsed ? 0 : 1,
                maxWidth: collapsed ? 0 : 200,
                pointerEvents: collapsed ? 'none' : 'auto',
              }}
            >
              <p style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.2em', color: 'var(--oc-muted)' }}>Prospect</p>
              <p style={{ fontSize: '0.875rem', fontWeight: 800, color: 'var(--oc-accent-ink)', lineHeight: 1 }}>Console</p>
              <div style={{ marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <p style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--oc-text)' }}>
                  {activeCampaign ? activeCampaign.name : <span style={{ color: 'var(--oc-muted)', fontWeight: 400 }}>Select campaign…</span>}
                </p>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                  style={{ flexShrink: 0, color: 'var(--oc-muted)', opacity: collapsed ? 0 : 1 }}>
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
            </button>
          </div>

          {dropdownOpen && (
            <div className="oc-nav-dropdown">
              <div className="oc-nav-dropdown-scroll">
                {campaigns.length === 0 && (
                  <p style={{ padding: '0.5rem 0.75rem', fontSize: '0.75rem', color: 'var(--oc-muted)' }}>No campaigns yet.</p>
                )}
                {campaigns.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => { onSelectCampaign(c.id); setDropdownOpen(false) }}
                    className="oc-nav-dropdown-item"
                  >
                    <span
                      className="oc-nav-dropdown-dot"
                      style={{
                        backgroundColor: c.id === selectedCampaignId ? 'var(--oc-accent)' : 'transparent',
                        border: '1.5px solid var(--oc-border)',
                      }}
                    />
                    <span style={{
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      fontWeight: c.id === selectedCampaignId ? 600 : 400,
                      color: c.id === selectedCampaignId ? 'var(--oc-accent-ink)' : 'var(--oc-text)',
                    }}>
                      {c.name}
                    </span>
                  </button>
                ))}
              </div>
              <div className="oc-nav-dropdown-footer">
                <button
                  type="button"
                  onClick={() => { setActiveView('campaigns'); setDropdownOpen(false) }}
                  className="oc-nav-dropdown-link"
                >
                  Manage campaigns →
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, overflow: 'hidden', padding: '0 0.5rem' }} aria-label="Main navigation">
          {NAV_ITEMS.map(({ value, label, stageColor, Icon }) => {
            const isActive = activeView === value
            return (
              <button
                key={value}
                type="button"
                onClick={() => setActiveView(value)}
                title={collapsed ? label : undefined}
                className="oc-nav-item"
                data-active={isActive ? 'true' : 'false'}
                style={{
                  '--item-accent': stageColor ?? 'var(--oc-accent)',
                  justifyContent: collapsed ? 'center' : undefined,
                } as React.CSSProperties}
              >
                <Icon size={18} className="oc-icon-shrink" />
                <span style={{
                  overflow: 'hidden', whiteSpace: 'nowrap',
                  transition: 'max-width 200ms, opacity 200ms',
                  maxWidth: collapsed ? 0 : 200,
                  opacity: collapsed ? 0 : 1,
                }}>
                  {label}
                </span>
              </button>
            )
          })}
        </nav>

        {/* Collapse toggle */}
        <div style={{ marginTop: '0.75rem', borderTop: '1px solid var(--oc-border)', padding: '0.75rem 0.5rem 0' }}>
          <button
            type="button"
            onClick={onToggleCollapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="oc-nav-item"
            style={{ justifyContent: collapsed ? 'center' : 'flex-end' }}
          >
            {collapsed ? (
              <IconChevronRight size={16} className="oc-icon-shrink" />
            ) : (
              <>
                <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>Collapse</span>
                <IconChevronLeft size={16} className="oc-icon-shrink" />
              </>
            )}
          </button>
        </div>
      </div>
    </aside>
  )
}
