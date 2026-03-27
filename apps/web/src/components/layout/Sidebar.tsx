import type { StatsResponse, PromptRead } from '../../lib/types'
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

interface SidebarProps {
  activeView: ActiveView
  setActiveView: (v: ActiveView) => void
  stats: StatsResponse | null
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

function PipelineDot({ stats }: { stats: StatsResponse | null }) {
  if (!stats) return null
  const hasActive =
    stats.scrape.running > 0 || stats.scrape.queued > 0 ||
    stats.analysis.running > 0 || stats.analysis.queued > 0
  if (!hasActive) return null
  return (
    <span className="relative flex h-2 w-2 flex-shrink-0">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--oc-accent)] opacity-60" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--oc-accent)]" />
    </span>
  )
}

function SegmentedBar({ s }: { s: StatsResponse['scrape'] }) {
  const { total, completed, failed, site_unavailable } = s
  if (total === 0) return null
  const donePct = (completed / total) * 100
  const failPct = (failed / total) * 100
  const downPct = (site_unavailable / total) * 100
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-(--oc-border) flex">
      <div className="h-full bg-emerald-500 transition-[width] duration-500 shrink-0" style={{ width: `${donePct}%` }} />
      <div className="h-full bg-red-400 transition-[width] duration-500 shrink-0" style={{ width: `${failPct}%` }} />
      <div className="h-full bg-slate-400 transition-[width] duration-500 shrink-0" style={{ width: `${downPct}%` }} />
    </div>
  )
}

function PipelineMini({ stats }: { stats: StatsResponse | null }) {
  if (!stats) return null
  const { scrape, analysis } = stats
  if (scrape.total === 0 && analysis.total === 0) return null
  const hasActive = scrape.running > 0 || scrape.queued > 0 || analysis.running > 0 || analysis.queued > 0

  return (
    <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-3">
      <div className="mb-2 flex items-center gap-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">Pipeline</p>
        {hasActive && <PipelineDot stats={stats} />}
      </div>
      <div className="space-y-3">
        {([
          { label: 'Scrape', s: scrape },
          { label: 'Analysis', s: analysis },
        ] as const).map(({ label, s }) => (
          <div key={label}>
            {/* Header: label + done/total */}
            <div className="mb-1 flex items-center justify-between gap-1">
              <span className="text-[11px] text-(--oc-muted)">{label}</span>
              <span className="font-mono text-[10px] tabular-nums text-(--oc-muted)">
                <span className="text-emerald-600 font-semibold">{s.completed.toLocaleString()}</span>
                <span className="text-(--oc-border)">/{s.total.toLocaleString()}</span>
              </span>
            </div>

            {/* Segmented bar: green=done, red=failed, gray=down, bg=remaining */}
            <SegmentedBar s={s} />

            {/* Legend row */}
            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-(--oc-muted)">
              {s.failed > 0 && (
                <span className="text-red-500">{s.failed.toLocaleString()} failed</span>
              )}
              {s.site_unavailable > 0 && (
                <span className="text-slate-400">{s.site_unavailable.toLocaleString()} down</span>
              )}
              {(s.running > 0 || s.queued > 0) && (
                <span className="text-(--oc-info-text)">
                  {s.running > 0 && `${s.running} running`}
                  {s.running > 0 && s.queued > 0 && ' · '}
                  {s.queued > 0 && `${s.queued} queued`}
                </span>
              )}
            </div>

            {/* ETA */}
            {s.eta_seconds != null && s.eta_seconds > 0 && (
              <p className="mt-0.5 text-[10px] text-(--oc-muted)">
                ETA {(() => {
                  const t = Math.round(s.eta_seconds!)
                  const h = Math.floor(t / 3600)
                  const m = Math.floor((t % 3600) / 60)
                  const s = t % 60
                  if (h > 0) return `${h}h ${m}m`
                  if (m > 0) return `${m}m ${s}s`
                  return `${s}s`
                })()}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function Sidebar({
  activeView,
  setActiveView,
  stats,
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

          {/* Pipeline widget — full when expanded, just dot when collapsed */}
          {collapsed ? (
            <div className="flex justify-center py-1">
              <PipelineDot stats={stats} />
            </div>
          ) : (
            <PipelineMini stats={stats} />
          )}

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
