import { useState } from 'react'
import type { CompanyList, CompanyListItem, ScrapeSubFilter, StatsResponse } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { SortableHeader } from '../../ui/SortableHeader'

interface S1ScrapingViewProps {
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  scrapeSubFilter: ScrapeSubFilter
  selectedIds: string[]
  totalMatching: number | null
  isLoading: boolean
  isScraping: boolean
  isSelectingAll: boolean
  stats: StatsResponse | null
  isResettingStuck: boolean
  isDrainingQueue: boolean
  actionState: Record<string, string>
  onScrapeSubFilterChange: (filter: ScrapeSubFilter) => void
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onScrapeSelected: () => void
  onScrapeOne: (company: CompanyListItem) => void
  onOpenDiagnostics: (company: CompanyListItem) => void
  onResetStuck: () => void
  onDrainQueue: () => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
}

const SUB_FILTERS: Array<{ value: ScrapeSubFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Not scraped' },
  { value: 'active', label: 'In progress' },
  { value: 'done', label: 'Done' },
  { value: 'failed', label: 'Failed' },
]

function scrapeBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === 'completed') return 'bg-emerald-50 text-emerald-800'
  if (s === 'running') return 'bg-blue-50 text-blue-800'
  if (s === 'queued' || s === 'created') return 'bg-amber-50 text-amber-800'
  if (s === 'failed' || s === 'dead' || s === 'step1_failed') return 'bg-rose-50 text-rose-800'
  if (s === 'cancelled') return 'bg-slate-100 text-slate-500'
  if (s === 'site_unavailable') return 'bg-orange-50 text-orange-800'
  return 'bg-slate-100 text-slate-600'
}

export function S1ScrapingView({
  companies,
  letterCounts,
  activeLetters,
  scrapeSubFilter,
  selectedIds,
  totalMatching,
  isLoading,
  isScraping,
  isSelectingAll,
  stats,
  isResettingStuck,
  isDrainingQueue,
  actionState,
  onScrapeSubFilterChange,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onScrapeSelected,
  onScrapeOne,
  onOpenDiagnostics,
  onResetStuck,
  onDrainQueue,
  sortBy,
  sortDir,
  onSort,
}: S1ScrapingViewProps) {
  const [search, setSearch] = useState('')
  const selectedSet = new Set(selectedIds)

  // 'active' is the only filter that can't be done server-side (no API equivalent),
  // so we client-filter on the loaded page. All other filters are applied server-side.
  const visibleCompanies = (companies?.items ?? []).filter((c) => {
    if (search && !c.domain.toLowerCase().includes(search.toLowerCase())) return false
    const letterOk = activeLetters.size === 0 || activeLetters.has(c.domain[0].toLowerCase())
    if (!letterOk) return false
    if (scrapeSubFilter === 'active') {
      const s = c.latest_scrape_status?.toLowerCase() ?? ''
      return s === 'queued' || s === 'created' || s === 'running'
    }
    return true
  })

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  // Only client-side sub-filters count as "sub-filtered" for the total count/select-all logic
  const isClientFiltered = scrapeSubFilter === 'active' || search !== ''
  const displayCount = isClientFiltered ? visibleCompanies.length : (companies?.total ?? 0)
  const effectiveTotalMatching = isClientFiltered ? visibleCompanies.length : totalMatching

  // Pipeline progress from stats
  const scrape = stats?.scrape
  const running = scrape?.running ?? 0
  const queued = scrape?.queued ?? 0
  const completed = scrape?.completed ?? 0
  const failed = scrape?.failed ?? 0
  const total = scrape?.total ?? 0
  const pctDone = scrape?.pct_done ?? 0
  const hasActivity = running > 0 || queued > 0

  return (
    <div className="space-y-3">
      {/* Pipeline progress banner */}
      {scrape && (hasActivity || completed > 0) && (
        <div className="rounded-2xl border border-(--oc-border) bg-white p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-(--oc-muted)">
                Scraping Pipeline
              </span>
              {hasActivity && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                  Active
                </span>
              )}
            </div>
            <span className="text-[11px] text-(--oc-muted)">
              {completed.toLocaleString()} / {total.toLocaleString()}
            </span>
          </div>
          {/* Progress track */}
          <div className="h-1.5 overflow-hidden rounded-full bg-(--oc-surface)" style={{ border: '1px solid var(--oc-border)' }}>
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(pctDone, 100)}%`,
                background: hasActivity
                  ? 'linear-gradient(90deg, var(--s1), #3b82f6)'
                  : '#16a34a',
              }}
            />
          </div>
          {/* Stat row */}
          <div className="mt-2.5 flex gap-5 text-[11px]">
            {running > 0 && (
              <span className="font-bold text-amber-600">{running.toLocaleString()} <span className="font-normal text-(--oc-muted)">running</span></span>
            )}
            {queued > 0 && (
              <span className="font-bold text-(--oc-muted)">{queued.toLocaleString()} <span className="font-normal">queued</span></span>
            )}
            <span className="font-bold text-emerald-700">{completed.toLocaleString()} <span className="font-normal text-(--oc-muted)">done</span></span>
            {failed > 0 && (
              <span className="font-bold text-rose-600">{failed.toLocaleString()} <span className="font-normal text-(--oc-muted)">failed</span></span>
            )}
            {scrape.stuck_count > 0 && (
              <button
                type="button"
                onClick={onResetStuck}
                disabled={isResettingStuck}
                className="ml-auto text-[11px] text-rose-500 underline underline-offset-2 transition hover:text-rose-700 disabled:opacity-50"
              >
                {isResettingStuck ? 'Resetting…' : `${scrape.stuck_count} stuck — reset`}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center gap-2 rounded-xl px-3 py-2.5" style={{ borderLeft: '3px solid var(--s1)', backgroundColor: 'var(--s1-bg)' }}>
        <div className="flex-1">
          <h2 className="text-base font-bold" style={{ color: 'var(--s1-text)' }}>S1 · Scraping</h2>
          <p className="text-xs" style={{ color: 'var(--s1-text)', opacity: 0.7 }}>
            Web content extraction · {companies != null ? `${displayCount.toLocaleString()} companies` : '—'}
          </p>
        </div>
        {/* Search */}
        <div className="relative">
          <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search domains…"
            className="rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--s1) focus:bg-white"
            style={{ width: 180 }}
          />
        </div>
      </div>

      {/* Letter strip */}
      <LetterStrip
        multiSelect
        activeLetters={activeLetters}
        counts={letterCounts}
        onToggle={onToggleLetter}
        onClear={onClearLetters}
      />

      {/* Sub-filter chips */}
      <div className="flex flex-wrap gap-1.5">
        {SUB_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => onScrapeSubFilterChange(f.value)}
            className={`rounded-full px-3 py-1 text-[11px] font-bold transition ${
              scrapeSubFilter === f.value
                ? 'text-white'
                : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s1) hover:text-(--s1-text)'
            }`}
            style={scrapeSubFilter === f.value ? { backgroundColor: 'var(--s1)' } : {}}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Selection bar */}
      <SelectionBar
        stageColor="--s1"
        stageBg="--s1-bg"
        selectedCount={selectedIds.length}
        totalMatching={effectiveTotalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedIds.length > 0 && !isClientFiltered ? onSelectAllMatching : null}
        isSelectingAll={isSelectingAll}
        onClear={onClearSelection}
      >
        <button
          type="button"
          onClick={onScrapeSelected}
          disabled={isScraping || selectedIds.length === 0}
          className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
          style={{ backgroundColor: 'var(--s1)' }}
        >
          {isScraping ? 'Queuing…' : 'Scrape Selected'}
        </button>
      </SelectionBar>

      {/* Table */}
      <div className="oc-panel overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-(--oc-border) text-[10px] uppercase tracking-wider text-(--oc-muted)">
              <th className="w-8 p-3">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                  onChange={() =>
                    onToggleAll(allVisibleSelected ? [] : visibleCompanies.map((c) => c.id))
                  }
                  className="cursor-pointer"
                />
              </th>
              <SortableHeader label="Domain" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Scrape status" field="scrape_status" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <th className="p-3 text-left font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 8 }).map((_, i) => (
              <tr key={i} className="border-b border-(--oc-border)">
                <td className="p-3"><div className="oc-skeleton h-4 w-4 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-36 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-5 w-20 rounded-full" /></td>
                <td className="p-3"><div className="oc-skeleton h-6 w-16 rounded-lg" /></td>
              </tr>
            ))}
            {!isLoading && visibleCompanies.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-10 text-center">
                  {scrapeSubFilter === 'pending' && companies != null ? (
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-emerald-700">All companies have been scraped ✓</p>
                      <p className="text-xs text-(--oc-muted)">Switch to "All" or "Done" to review results.</p>
                    </div>
                  ) : scrapeSubFilter === 'failed' ? (
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-(--oc-text)">No failed scrapes</p>
                      <p className="text-xs text-(--oc-muted)">All scrapes completed successfully.</p>
                    </div>
                  ) : (
                    <p className="text-sm text-(--oc-muted)">No companies match this filter.</p>
                  )}
                </td>
              </tr>
            )}
            {visibleCompanies.map((c) => (
              <tr
                key={c.id}
                className="border-b border-(--oc-border) last:border-0 transition"
                style={selectedSet.has(c.id) ? { backgroundColor: 'var(--s1-bg)' } : {}}
              >
                <td className="p-3">
                  <input
                    type="checkbox"
                    checked={selectedSet.has(c.id)}
                    onChange={() => onToggleRow(c.id)}
                    className="cursor-pointer"
                  />
                </td>
                <td className="p-3">
                  <a
                    href={c.normalized_url || c.raw_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[12px] font-medium hover:underline"
                    style={{ color: 'var(--s1)' }}
                  >
                    {c.domain}
                  </a>
                </td>
                <td className="p-3">
                  {c.latest_scrape_status ? (
                    <Badge className={scrapeBadgeClass(c.latest_scrape_status)}>
                      {c.latest_scrape_status}
                    </Badge>
                  ) : (
                    <span className="text-xs text-(--oc-muted)">not scraped</span>
                  )}
                </td>
                <td className="p-3">
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => onScrapeOne(c)}
                      disabled={!!actionState[c.id]}
                      className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s1) hover:text-(--s1-text) disabled:opacity-50"
                    >
                      {actionState[c.id] ?? 'Scrape'}
                    </button>
                    {c.latest_scrape_job_id && (
                      <button
                        type="button"
                        onClick={() => onOpenDiagnostics(c)}
                        className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s1) hover:text-(--s1-text)"
                      >
                        Diag
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pipeline ops (drain queue) */}
      {stats && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-(--oc-border) bg-white p-3">
          <p className="mr-2 text-xs font-bold text-(--oc-muted)">Pipeline ops</p>
          <button
            type="button"
            onClick={onDrainQueue}
            disabled={isDrainingQueue || stats.scrape.queued === 0}
            className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isDrainingQueue ? 'Draining…' : `Drain Queue (${stats.scrape.queued})`}
          </button>
        </div>
      )}
    </div>
  )
}
