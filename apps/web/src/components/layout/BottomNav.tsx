import { useState } from 'react'
import type { ActiveView } from '../../lib/navigation'
import { IconBuilding, IconGlobe, IconChart, IconPulse, IconPencil, IconDots, IconUsers } from '../ui/icons'

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

export function BottomNav({ activeView, setActiveView, onOpenPromptLibrary }: BottomNavProps) {
  const [moreOpen, setMoreOpen] = useState(false)
  const moreActive = activeView === 'campaigns' || activeView === 's3-contacts' || activeView === 's4-validation'

  return (
    <>
      {moreOpen && (
        <div className="fixed inset-0 z-[var(--z-overlay)] md:hidden" onClick={() => setMoreOpen(false)} aria-hidden="true" />
      )}

      {moreOpen && (
        <div className="fixed bottom-[calc(var(--oc-bottom-nav-h)+10px)] right-3 z-[var(--z-drawer)] w-60 rounded-2xl border border-(--oc-border) bg-(--oc-surface-strong) p-2 shadow-[0_10px_30px_rgba(7,21,31,0.2)] md:hidden">
          <button
            type="button"
            onClick={() => {
              setActiveView('campaigns')
              setMoreOpen(false)
            }}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold transition ${
              activeView === 'campaigns'
                ? 'font-bold'
                : 'text-(--oc-muted) hover:bg-(--oc-surface)'
            }`}
            style={activeView === 'campaigns' ? { backgroundColor: 'var(--oc-accent-soft)', color: 'var(--oc-accent-ink)' } : {}}
          >
            <IconBuilding size={16} />
            Campaigns
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveView('s3-contacts')
              setMoreOpen(false)
            }}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold transition ${
              activeView === 's3-contacts'
                ? 'font-bold'
                : 'text-(--oc-muted) hover:bg-(--oc-surface)'
            }`}
            style={activeView === 's3-contacts' ? { backgroundColor: 'var(--s3)22', color: 'var(--s3)' } : {}}
          >
            <IconUsers size={16} />
            S3 · Contacts
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveView('s4-validation')
              setMoreOpen(false)
            }}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold transition ${
              activeView === 's4-validation'
                ? 'font-bold'
                : 'text-(--oc-muted) hover:bg-(--oc-surface)'
            }`}
            style={activeView === 's4-validation' ? { backgroundColor: 'var(--s4)22', color: 'var(--s4)' } : {}}
          >
            <IconBuilding size={16} />
            S4 · Validation
          </button>
          <button
            type="button"
            onClick={() => {
              setMoreOpen(false)
              onOpenPromptLibrary()
            }}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold text-(--oc-muted) transition hover:bg-(--oc-surface)"
          >
            <IconPencil size={16} />
            Prompt Library
          </button>
        </div>
      )}

      <nav
        className="
          md:hidden fixed bottom-0 inset-x-0 z-[var(--z-toolbar)]
          flex items-stretch border-t border-(--oc-border)
          bg-(--oc-surface-strong) backdrop-blur-sm
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
                className={isActive ? 'text-(--oc-accent)' : 'text-(--oc-muted)'}
              />
              <span
                className={`text-[10px] font-bold tracking-wide ${
                  isActive ? 'text-(--oc-accent)' : 'text-(--oc-muted)'
                }`}
              >
                {label}
              </span>
              {isActive && (
                <span className="absolute bottom-0 h-0.5 w-6 rounded-full bg-(--oc-accent)" />
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
          <IconDots size={22} className={moreOpen || moreActive ? 'text-(--oc-accent)' : 'text-(--oc-muted)'} />
          <span className={`text-[10px] font-bold tracking-wide ${moreOpen || moreActive ? 'text-(--oc-accent)' : 'text-(--oc-muted)'}`}>
            More
          </span>
          {(moreOpen || moreActive) && (
            <span className="absolute bottom-0 h-0.5 w-6 rounded-full bg-(--oc-accent)" />
          )}
        </button>
      </nav>
    </>
  )
}
