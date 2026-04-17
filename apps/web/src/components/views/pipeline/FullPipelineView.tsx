import { useState } from 'react'
import type { CompanyList, CompanyListItem } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'

// ── Status helpers ────────────────────────────────────────────────────────────

type BadgeVariant = 'ok' | 'run' | 'err' | 'neu' | 'warn'

interface CellStatus {
  label: string
  variant: BadgeVariant
}

function s1Status(c: CompanyListItem): CellStatus {
  const s = c.latest_scrape_status?.toLowerCase()
  if (!s) return { label: '—', variant: 'neu' }
  if (s === 'completed') return { label: 'Done', variant: 'ok' }
  if (s === 'created') return { label: 'Queued', variant: 'run' }
  if (s === 'running') return { label: 'Scraping…', variant: 'run' }
  if (s === 'cancelled') return { label: 'Cancelled', variant: 'neu' }
  if (s === 'site_unavailable') return { label: 'Unavailable', variant: 'err' }
  if (s === 'failed' || s === 'step1_failed') return { label: 'Failed', variant: 'err' }
  return { label: s, variant: 'neu' }
}

function s2Status(c: CompanyListItem): CellStatus {
  const label = (c.feedback_manual_label ?? c.latest_decision ?? '').toLowerCase()
  if (label === 'possible') return { label: 'Approved', variant: 'ok' }
  if (label === 'crap') return { label: 'Rejected', variant: 'err' }
  if (label === 'unknown') return { label: 'Unknown', variant: 'neu' }

  const as = c.latest_analysis_status?.toLowerCase()
  if (as === 'running' || as === 'queued') return { label: 'Analysing…', variant: 'run' }
  if (as === 'dead') return { label: 'Stuck', variant: 'warn' }
  if (as === 'failed') return { label: 'Failed', variant: 'err' }
  return { label: 'Waiting', variant: 'neu' }
}

function s3Status(c: CompanyListItem): CellStatus {
  if (c.contact_count > 0) return { label: `${c.contact_count} contacts`, variant: 'ok' }
  const cs = c.contact_fetch_status?.toLowerCase()
  if (cs === 'running' || cs === 'queued') return { label: 'Fetching…', variant: 'run' }
  if (cs === 'succeeded') return { label: 'Fetched (0)', variant: 'neu' }
  if (cs === 'failed') return { label: 'Failed', variant: 'err' }
  return { label: 'Waiting', variant: 'neu' }
}

function s4Status(c: CompanyListItem): CellStatus {
  if (c.pipeline_stage === 'contact_ready' && c.contact_count > 0) {
    return { label: `${c.contact_count} to verify`, variant: 'neu' }
  }
  return { label: '—', variant: 'neu' }
}

// ── Status filter ─────────────────────────────────────────────────────────────

// StatusFilter values based on actual DB values found in scrapejob + analysis_jobs:
// scrape statuses: 'completed', 'cancelled', 'site_unavailable', 'failed', 'created', null
// analysis states: 'SUCCEEDED', 'DEAD', 'FAILED' (uppercase enum)
// predicted_label: 'POSSIBLE', 'CRAP', 'UNKNOWN' (uppercase)
// contact_fetch state: 'succeeded', 'failed' (lowercase)
type StatusFilter = 'all' | 'not-started' | 'in-progress' | 'cancelled' | 'complete' | 'has-failures'

function matchesStatus(c: CompanyListItem, f: StatusFilter): boolean {
  if (f === 'all') return true

  const scrape = c.latest_scrape_status?.toLowerCase()
  const analysis = c.latest_analysis_status?.toLowerCase()
  const contact = c.contact_fetch_status?.toLowerCase()

  if (f === 'not-started') return !scrape
  if (f === 'cancelled') return scrape === 'cancelled'
  if (f === 'in-progress')
    return (
      scrape === 'created' ||
      analysis === 'queued' ||
      analysis === 'running' ||
      contact === 'queued' ||
      contact === 'running'
    )
  if (f === 'complete')
    return scrape === 'completed' && !!(c.feedback_manual_label ?? c.latest_decision)
  if (f === 'has-failures')
    return (
      scrape === 'failed' ||
      scrape === 'step1_failed' ||
      scrape === 'site_unavailable' ||
      analysis === 'failed' ||
      analysis === 'dead' ||
      contact === 'failed'
    )
  return true
}

// ── Badge component ───────────────────────────────────────────────────────────

const BADGE_CLS: Record<BadgeVariant, string> = {
  ok:   'bg-emerald-50 text-emerald-800 border border-emerald-200',
  run:  'bg-amber-50 text-amber-800 border border-amber-200',
  err:  'bg-rose-50 text-rose-700 border border-rose-200',
  warn: 'bg-orange-50 text-orange-700 border border-orange-200',
  neu:  'bg-slate-100 text-slate-500 border border-slate-200',
}

const DOT_CLS: Record<BadgeVariant, string> = {
  ok: 'bg-emerald-600', run: 'bg-amber-500', err: 'bg-rose-500',
  warn: 'bg-orange-500', neu: 'bg-slate-400',
}

function StatusBadge({ label, variant }: CellStatus) {
  if (label === '—') return <span className="text-xs text-slate-300">—</span>
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-bold ${BADGE_CLS[variant]}`}>
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${DOT_CLS[variant]} ${variant === 'run' ? 'animate-pulse' : ''}`} />
      {label}
    </span>
  )
}

// ── Stage column headers ──────────────────────────────────────────────────────

const STAGES = [
  { num: 1, label: 'Scraping',     colorVar: '--s1', bgVar: '--s1-bg', textVar: '--s1-text' },
  { num: 2, label: 'AI Decision',  colorVar: '--s2', bgVar: '--s2-bg', textVar: '--s2-text' },
  { num: 3, label: 'Contact Fetch',colorVar: '--s3', bgVar: '--s3-bg', textVar: '--s3-text' },
  { num: 4, label: 'Validation',   colorVar: '--s4', bgVar: '--s4-bg', textVar: '--s4-text' },
] as const

const STATUS_FILTERS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'not-started', label: 'Not started' },
  { value: 'in-progress', label: 'In progress' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'complete', label: 'Complete' },
  { value: 'has-failures', label: 'Has failures' },
]

// ── Props ─────────────────────────────────────────────────────────────────────

interface FullPipelineViewProps {
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetter: string | null
  selectedIds: string[]
  isLoading: boolean
  onLetterChange: (l: string | null) => void
  onToggleRow: (id: string) => void
  onToggleAll: (ids: string[]) => void
  onClearSelection: () => void
  onScrapeSelected: () => void
  isScraping: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────

export function FullPipelineView({
  companies,
  letterCounts,
  activeLetter,
  selectedIds,
  isLoading,
  onLetterChange,
  onToggleRow,
  onToggleAll,
  onClearSelection,
  onScrapeSelected,
  isScraping,
}: FullPipelineViewProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [search, setSearch] = useState('')
  const selectedSet = new Set(selectedIds)

  const allItems = companies?.items ?? []

  const visible = allItems.filter((c) => {
    if (search && !c.domain.toLowerCase().includes(search.toLowerCase())) return false
    if (!matchesStatus(c, statusFilter)) return false
    return true
  })

  const allVisibleSelected = visible.length > 0 && visible.every((c) => selectedSet.has(c.id))
  const someVisibleSelected = !allVisibleSelected && visible.some((c) => selectedSet.has(c.id))

  return (
    <div className="flex h-full flex-col gap-0 overflow-hidden">
      {/* Topbar */}
      <div className="flex shrink-0 items-center gap-2 border-b border-(--oc-border) px-1 py-2">
        <span className="text-sm font-extrabold tracking-tight text-(--oc-accent-ink)">
          Full Pipeline
        </span>
        {companies?.total != null && (
          <span className="text-xs text-(--oc-muted)">{companies.total.toLocaleString()} domains</span>
        )}
        <div className="relative ml-1 flex-1 max-w-72">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search domains…"
            className="w-full rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--oc-accent) focus:bg-white"
          />
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-(--oc-border) px-1 py-2">
        <LetterStrip
          active={activeLetter}
          onChange={onLetterChange}
          counts={letterCounts}
        />
        <span className="h-5 w-px bg-(--oc-border)" />
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setStatusFilter(f.value)}
              className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                statusFilter === f.value
                  ? 'border border-(--oc-accent) bg-(--oc-accent-soft) text-(--oc-accent-ink)'
                  : 'border border-(--oc-border) bg-white text-(--oc-muted) hover:border-(--oc-accent) hover:text-(--oc-accent-ink)'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Selection bar */}
      {selectedIds.length > 0 && (
        <div className="flex shrink-0 items-center gap-2 border-b border-(--oc-border) bg-(--oc-accent-soft) px-3 py-2 text-sm"
          style={{ animation: 'sel-slide-in 120ms ease-out' }}
        >
          <span className="inline-flex items-center gap-1.5 rounded-full bg-(--oc-accent) px-2.5 py-0.5 text-xs font-bold text-white">
            {selectedIds.length.toLocaleString()} selected
          </span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={onScrapeSelected}
            disabled={isScraping}
            className="rounded-lg bg-(--oc-accent) px-3 py-1.5 text-xs font-bold text-white transition hover:opacity-90 disabled:opacity-60"
          >
            {isScraping ? 'Queuing…' : 'Scrape selected'}
          </button>
          <button
            type="button"
            onClick={onClearSelection}
            className="text-xs text-(--oc-muted) underline underline-offset-2 hover:text-(--oc-text)"
          >
            Clear
          </button>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <div className="min-w-180">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-(--oc-border) bg-white/95 backdrop-blur-sm">
                <th className="w-10 p-3 pl-4">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                    onChange={() => onToggleAll(allVisibleSelected ? [] : visible.map((c) => c.id))}
                    className="cursor-pointer accent-(--oc-accent)"
                  />
                </th>
                <th className="min-w-52 p-3 text-left text-[10.5px] font-bold uppercase tracking-widest text-(--oc-muted)">
                  Domain
                </th>
                {STAGES.map((s) => (
                  <th
                    key={s.num}
                    className="min-w-36 p-3 text-left"
                    style={{ background: `color-mix(in srgb, var(${s.bgVar}) 35%, white)` }}
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className="flex h-4.25 w-4.25 shrink-0 items-center justify-center rounded-full text-[9.5px] font-black"
                        style={{ background: `var(${s.bgVar})`, color: `var(${s.textVar})` }}
                      >
                        {s.num}
                      </span>
                      <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color: `var(${s.textVar})` }}>
                        {s.label}
                      </span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-sm text-(--oc-muted)">Loading…</td>
                </tr>
              )}
              {!isLoading && visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-sm text-(--oc-muted)">
                    No companies match this filter.
                  </td>
                </tr>
              )}
              {visible.map((c) => {
                const isSelected = selectedSet.has(c.id)
                return (
                  <tr
                    key={c.id}
                    className={`border-b border-(--oc-border)/60 last:border-0 transition-colors ${
                      isSelected
                        ? 'bg-(--oc-accent-soft)/40'
                        : 'hover:bg-(--oc-accent-soft)/20'
                    }`}
                  >
                    <td className="p-3 pl-4">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => onToggleRow(c.id)}
                        className="cursor-pointer accent-(--oc-accent)"
                      />
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-(--oc-border) bg-(--oc-surface) text-[11px] font-bold text-(--oc-accent-ink)">
                          {c.domain[0].toUpperCase()}
                        </div>
                        <div>
                          <p className="font-mono text-xs font-medium text-(--oc-text)">{c.domain}</p>
                          <p className="text-[10.5px] text-(--oc-muted)">
                            Added {new Date(c.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="p-3"><StatusBadge {...s1Status(c)} /></td>
                    <td className="p-3"><StatusBadge {...s2Status(c)} /></td>
                    <td className="p-3"><StatusBadge {...s3Status(c)} /></td>
                    <td className="p-3"><StatusBadge {...s4Status(c)} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination info */}
      {companies && (
        <div className="flex shrink-0 items-center justify-between border-t border-(--oc-border) px-4 py-2.5 text-xs text-(--oc-muted)">
          <span>
            Showing {visible.length.toLocaleString()} of {(companies.total ?? 0).toLocaleString()} domains
          </span>
          {companies.has_more && (
            <span className="text-xs text-(--oc-accent)">Scroll or adjust letter filter to see more</span>
          )}
        </div>
      )}
    </div>
  )
}
