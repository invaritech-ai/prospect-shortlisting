import { useState } from 'react'
import type { ActiveView } from '../../lib/navigation'
import { IconBuilding, IconGlobe, IconChart, IconTimeline, IconPulse, IconPencil, IconDots, IconUsers } from '../ui/icons'

interface BottomNavProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  onOpenPromptLibrary: () => void
}

const NAV_ITEMS = [
  { value: 'companies' as const, label: 'Companies', Icon: IconBuilding },
  { value: 'jobs' as const, label: 'Scrape', Icon: IconGlobe },
  { value: 'runs' as const, label: 'Analysis', Icon: IconChart },
]

export function BottomNav({ activeView, setActiveView, onOpenPromptLibrary }: BottomNavProps) {
  const [moreOpen, setMoreOpen] = useState(false)
  const moreActive = activeView === 'operations' || activeView === 'analytics' || activeView === 'contacts'

  return (
    <>
      {moreOpen && (
        <div className="fixed inset-0 z-[var(--z-overlay)] md:hidden" onClick={() => setMoreOpen(false)} aria-hidden="true" />
      )}

      {moreOpen && (
        <div className="fixed bottom-[calc(var(--oc-bottom-nav-h)+10px)] right-3 z-[var(--z-drawer)] w-60 rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface-strong)] p-2 shadow-[0_10px_30px_rgba(7,21,31,0.2)] md:hidden">
          <button
            type="button"
            onClick={() => {
              setActiveView('contacts')
              setMoreOpen(false)
            }}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold transition ${
              activeView === 'contacts'
                ? 'bg-[var(--oc-accent-soft)] text-[var(--oc-accent-ink)]'
                : 'text-[var(--oc-muted)] hover:bg-[var(--oc-surface)]'
            }`}
          >
            <IconUsers size={16} />
            Contacts
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveView('operations')
              setMoreOpen(false)
            }}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold transition ${
              activeView === 'operations'
                ? 'bg-[var(--oc-accent-soft)] text-[var(--oc-accent-ink)]'
                : 'text-[var(--oc-muted)] hover:bg-[var(--oc-surface)]'
            }`}
          >
            <IconTimeline size={16} />
            Operations Log
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveView('analytics')
              setMoreOpen(false)
            }}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold transition ${
              activeView === 'analytics'
                ? 'bg-[var(--oc-accent-soft)] text-[var(--oc-accent-ink)]'
                : 'text-[var(--oc-muted)] hover:bg-[var(--oc-surface)]'
            }`}
          >
            <IconPulse size={16} />
            Analytics Snapshot
          </button>
          <button
            type="button"
            onClick={() => {
              setMoreOpen(false)
              onOpenPromptLibrary()
            }}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold text-[var(--oc-muted)] transition hover:bg-[var(--oc-surface)]"
          >
            <IconPencil size={16} />
            Prompt Library
          </button>
        </div>
      )}

      <nav
        className="
          md:hidden fixed bottom-0 inset-x-0 z-[var(--z-toolbar)]
          flex items-stretch border-t border-[var(--oc-border)]
          bg-[var(--oc-surface-strong)] backdrop-blur-sm
        "
        style={{ height: 'var(--oc-bottom-nav-h)' }}
        aria-label="Mobile navigation"
      >
        {NAV_ITEMS.map(({ value, label, Icon }) => {
          const isActive = activeView === value
          return (
            <button
              key={value}
              type="button"
              onClick={() => {
                setActiveView(value)
                setMoreOpen(false)
              }}
              className="relative flex flex-1 flex-col items-center justify-center gap-0.5 transition"
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon
                size={22}
                className={isActive ? 'text-[var(--oc-accent)]' : 'text-[var(--oc-muted)]'}
              />
              <span
                className={`text-[10px] font-bold tracking-wide ${
                  isActive ? 'text-[var(--oc-accent)]' : 'text-[var(--oc-muted)]'
                }`}
              >
                {label}
              </span>
              {isActive && (
                <span className="absolute bottom-0 h-0.5 w-6 rounded-full bg-[var(--oc-accent)]" />
              )}
            </button>
          )
        })}

        <button
          type="button"
          onClick={() => setMoreOpen((prev) => !prev)}
          className="relative flex flex-1 flex-col items-center justify-center gap-0.5 transition"
          aria-expanded={moreOpen}
          aria-label="More navigation options"
        >
          <IconDots size={22} className={moreOpen || moreActive ? 'text-[var(--oc-accent)]' : 'text-[var(--oc-muted)]'} />
          <span className={`text-[10px] font-bold tracking-wide ${moreOpen || moreActive ? 'text-[var(--oc-accent)]' : 'text-[var(--oc-muted)]'}`}>
            More
          </span>
          {(moreOpen || moreActive) && (
            <span className="absolute bottom-0 h-0.5 w-6 rounded-full bg-[var(--oc-accent)]" />
          )}
        </button>
      </nav>
    </>
  )
}
