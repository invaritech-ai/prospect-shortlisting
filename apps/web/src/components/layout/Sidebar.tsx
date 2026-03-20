import type { StatsResponse, PromptRead } from '../../lib/types'
import { IconBuilding, IconGlobe, IconChart, IconPencil, IconDownload, IconChevronLeft, IconChevronRight } from '../ui/icons'

type ActiveView = 'companies' | 'jobs' | 'runs'

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

function PipelineMini({ stats }: { stats: StatsResponse | null }) {
  if (!stats) return null
  const { scrape, analysis } = stats
  if (scrape.total === 0 && analysis.total === 0) return null
  const hasActive = scrape.running > 0 || scrape.queued > 0 || analysis.running > 0 || analysis.queued > 0

  return (
    <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-3">
      <div className="mb-2 flex items-center gap-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Pipeline</p>
        {hasActive && <PipelineDot stats={stats} />}
      </div>
      <div className="space-y-2">
        {[
          { label: 'Scrape', s: scrape },
          { label: 'Analysis', s: analysis },
        ].map(({ label, s }) => (
          <div key={label}>
            <div className="mb-1 flex items-center justify-between gap-1">
              <span className="text-[11px] text-[var(--oc-muted)]">{label}</span>
              <span className="font-mono text-[10px] tabular-nums text-[var(--oc-muted)]">{s.pct_done}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[var(--oc-border)]">
              <div
                className="h-full rounded-full bg-[var(--oc-accent)] transition-[width] duration-500"
                style={{ width: `${Math.min(s.pct_done, 100)}%` }}
              />
            </div>
            {(s.running > 0 || s.queued > 0 || s.failed > 0 || s.site_unavailable > 0) && (
              <p className="mt-0.5 text-[10px] text-[var(--oc-muted)]">
                {s.running > 0 && <span className="text-[var(--oc-info-text)]">{s.running} running</span>}
                {s.running > 0 && s.queued > 0 && ' · '}
                {s.queued > 0 && `${s.queued} queued`}
                {s.failed > 0 && <span className="text-[var(--oc-fail-text)]"> · {s.failed} failed</span>}
                {s.site_unavailable > 0 && ` · ${s.site_unavailable} down`}
              </p>
            )}
            {s.eta_seconds != null && s.eta_seconds > 0 && (
              <p className="mt-0.5 text-[10px] text-[var(--oc-muted)]">
                ETA: {Math.floor(s.eta_seconds / 60)}m {Math.round(s.eta_seconds % 60)}s
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
          <div
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg font-extrabold text-white text-sm"
            style={{ background: 'var(--oc-accent)' }}
          >
            PS
          </div>
          {/* Label fades + slides out */}
          <div
            className="overflow-hidden transition-all duration-200"
            style={{
              opacity: collapsed ? 0 : 1,
              maxWidth: collapsed ? 0 : 200,
              whiteSpace: 'nowrap',
            }}
          >
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--oc-muted)]">Prospect</p>
            <p className="text-sm font-extrabold text-[var(--oc-accent-ink)] leading-none">Pipeline</p>
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
              <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Active Prompt</p>
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
                <p className="mt-1.5 text-xs text-[var(--oc-muted)]">No prompt selected</p>
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
