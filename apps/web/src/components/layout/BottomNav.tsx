import { useState } from 'react'
import type { ActiveView } from '../../lib/navigation'
import {
  IconBuilding, IconGlobe, IconChart, IconPulse, IconPencil,
  IconDots, IconCog, IconUsers, IconTimeline, IconSliders,
  IconCheck, IconZap,
} from '../ui/icons'

interface BottomNavProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  onOpenPromptLibrary: () => void
}

const NAV_ITEMS = [
  { value: 'dashboard' as const, label: 'Dashboard', Icon: IconPulse },
  { value: 's1-scraping' as const, label: 'Scraping', Icon: IconGlobe },
  { value: 's2-ai' as const, label: 'AI', Icon: IconChart },
]

const MORE_ITEMS: Array<{ value: ActiveView; label: string; stageColor?: string; Icon: typeof IconBuilding }> = [
  { value: 'campaigns',      label: 'Campaigns',             Icon: IconBuilding },
  { value: 'operations',     label: 'Operations',            Icon: IconTimeline },
  { value: 'settings',       label: 'Settings',              Icon: IconCog },
  { value: 'full-pipeline',  label: 'Full Pipeline',         Icon: IconSliders },
  { value: 's3-contacts',    label: 'S3 · Contacts & Emails',stageColor: 'var(--s3)', Icon: IconUsers },
  { value: 's4-reveal',      label: 'S4 · Retry Reveals',    stageColor: 'var(--s4)', Icon: IconZap },
  { value: 's5-validation',  label: 'S5 · Validation',       stageColor: 'var(--s5)', Icon: IconCheck },
]

export function BottomNav({ activeView, setActiveView, onOpenPromptLibrary }: BottomNavProps) {
  const [moreOpen, setMoreOpen] = useState(false)
  const moreActive = MORE_ITEMS.some((i) => i.value === activeView)

  return (
    <>
      {moreOpen && (
        <div
          className="fixed inset-0 md:hidden"
          style={{ zIndex: 'var(--z-overlay)' }}
          onClick={() => setMoreOpen(false)}
          aria-hidden="true"
        />
      )}

      {moreOpen && (
        <div className="oc-more-popup md:hidden">
          {MORE_ITEMS.map(({ value, label, stageColor, Icon }) => {
            const isActive = activeView === value
            return (
              <button
                key={value}
                type="button"
                onClick={() => { setActiveView(value); setMoreOpen(false) }}
                className="oc-more-popup-item"
                data-active={isActive ? 'true' : 'false'}
                style={isActive
                  ? { '--item-accent': stageColor ?? 'var(--oc-accent)' } as React.CSSProperties
                  : undefined}
              >
                <Icon size={16} />
                {label}
              </button>
            )
          })}
          <button
            type="button"
            onClick={() => { setMoreOpen(false); onOpenPromptLibrary() }}
            className="oc-more-popup-item"
          >
            <IconPencil size={16} />
            Prompt Library
          </button>
        </div>
      )}

      <nav className="oc-bottom-nav" aria-label="Mobile navigation">
        {NAV_ITEMS.map(({ value, label, Icon }) => {
          const isActive = activeView === value
          return (
            <button
              key={value}
              type="button"
              onClick={() => { setActiveView(value); setMoreOpen(false) }}
              className="oc-bottom-nav-item"
              data-active={isActive ? 'true' : 'false'}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon size={22} />
              <span>{label}</span>
              {isActive && <span className="oc-bottom-nav-pip" />}
            </button>
          )
        })}

        <button
          type="button"
          onClick={() => setMoreOpen((prev) => !prev)}
          className="oc-bottom-nav-item"
          data-active={(moreOpen || moreActive) ? 'true' : 'false'}
          aria-expanded={moreOpen}
          aria-label="More navigation options"
        >
          <IconDots size={22} />
          <span>More</span>
          {(moreOpen || moreActive) && <span className="oc-bottom-nav-pip" />}
        </button>
      </nav>
    </>
  )
}
