import { IconBuilding, IconGlobe, IconChart, IconPencil } from '../ui/icons'

type ActiveView = 'companies' | 'jobs' | 'runs'

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
  return (
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
            onClick={() => setActiveView(value)}
            className="flex flex-1 flex-col items-center justify-center gap-0.5 transition"
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

      {/* Prompt Library tab */}
      <button
        type="button"
        onClick={onOpenPromptLibrary}
        className="flex flex-1 flex-col items-center justify-center gap-0.5 transition"
      >
        <IconPencil size={22} className="text-[var(--oc-muted)]" />
        <span className="text-[10px] font-bold tracking-wide text-[var(--oc-muted)]">Prompts</span>
      </button>
    </nav>
  )
}
