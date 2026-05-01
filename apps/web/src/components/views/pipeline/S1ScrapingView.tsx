import type { CompanyCounts, CompanyList, CompanyListItem, ScrapePromptRead, ScrapeSubFilter, StatsResponse } from '../../../lib/types'
import { getDisplayedScrapeFailedCount } from '../../../lib/scrapeCounts'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { SortableHeader } from '../../ui/SortableHeader'
import { Pager } from '../../ui/Pager'
import { PipelineStageCompanyTableRow } from './PipelineStageCompanyTableRow'

interface S1ScrapingViewProps {
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  scrapeSubFilter: ScrapeSubFilter
  selectedScrapePrompt: ScrapePromptRead | null
  selectedIds: string[]
  totalMatching: number | null
  search: string
  isLoading: boolean
  isScraping: boolean
  isSelectingAll: boolean
  stats: StatsResponse | null
  companyCounts: CompanyCounts | null
  isResettingStuck: boolean
  isDrainingQueue: boolean
  actionState: Record<string, string>
  offset: number
  pageSize: number
  onScrapeSubFilterChange: (filter: ScrapeSubFilter) => void
  onSearchChange: (value: string) => void
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onScrapeSelected: () => void
  onScrapeOne: (company: CompanyListItem) => void
  onOpenPromptLibrary: () => void
  onOpenDiagnostics: (company: CompanyListItem) => void
  onResetStuck: () => void
  onDrainQueue: () => void
  onPagePrev: () => void
  onPageNext: () => void
  onPageSizeChange: (size: number) => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
}

const SUB_FILTERS: Array<{ value: ScrapeSubFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'not-started', label: 'Not started' },
  { value: 'in-progress', label: 'In progress' },
  { value: 'done', label: 'Done' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'permanent', label: 'Permanent fail' },
  { value: 'soft', label: 'Soft fail' },
]

function scrapeBadgeClass(status: string, failureReason?: string | null): string {
  const s = status.toLowerCase()
  if (s === 'succeeded') return 'bg-emerald-50 text-emerald-800'
  if (s === 'running') return 'bg-blue-50 text-blue-800'
  if (s === 'created') return 'bg-amber-50 text-amber-800'
  if (s === 'failed') {
    return failureReason === 'site_unavailable'
      ? 'bg-orange-50 text-orange-800'
      : 'bg-rose-50 text-rose-800'
  }
  if (s === 'cancelled') return 'bg-slate-100 text-slate-500'
  return 'bg-slate-100 text-slate-600'
}

function scrapeBadgeLabel(status: string, failureReason?: string | null): string {
  const s = status.toLowerCase()
  if (s === 'failed') {
    return failureReason === 'site_unavailable' ? 'failed (permanent)' : 'failed (soft)'
  }
  return status
}

export function S1ScrapingView({
  companies,
  letterCounts,
  activeLetters,
  scrapeSubFilter,
  selectedScrapePrompt,
  selectedIds,
  totalMatching,
  search,
  isLoading,
  isScraping,
  isSelectingAll,
  stats,
  companyCounts,
  isResettingStuck,
  isDrainingQueue,
  actionState,
  offset,
  pageSize,
  onScrapeSubFilterChange,
  onSearchChange,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onScrapeSelected,
  onScrapeOne,
  onOpenPromptLibrary,
  onOpenDiagnostics,
  onResetStuck,
  onDrainQueue,
  onPagePrev,
  onPageNext,
  onPageSizeChange,
  sortBy,
  sortDir,
  onSort,
}: S1ScrapingViewProps) {
  const selectedSet = new Set(selectedIds)
  const visibleCompanies = companies?.items ?? []
  const allVisibleSelected = visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected = !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))
  const displayCount = companies?.total ?? 0
  const effectiveTotalMatching = totalMatching ?? companies?.total ?? null

  // Pipeline progress from stats
  const scrape = stats?.scrape
  const total = scrape?.total ?? 0
  const pctDone = scrape?.pct_done ?? 0
  const counts = companyCounts
  const fallbackCounts = scrape ? {
    scrape_not_started: Math.max(
      0,
      total
        - (scrape.succeeded ?? 0)
        - (scrape.running ?? 0)
        - (scrape.queued ?? 0)
        - (scrape.site_unavailable ?? 0)
        - (scrape.failed ?? 0),
    ),
    scrape_in_progress: (scrape.running ?? 0) + (scrape.queued ?? 0),
    scrape_done: scrape.succeeded ?? 0,
    scrape_cancelled: 0,
    scrape_permanent_fail: scrape.site_unavailable ?? 0,
    scrape_soft_fail: Math.max(0, (scrape.failed ?? 0) - (scrape.site_unavailable ?? 0)),
    scrape_failed: scrape.failed ?? 0,
  } : null
  const summaryCounts = counts ?? fallbackCounts
  const failedCount = getDisplayedScrapeFailedCount(summaryCounts)
  const hasActivity = (scrape?.running ?? 0) > 0 || (scrape?.queued ?? 0) > 0

  return (
    <div className="space-y-3">
      {/* ── Sticky controls (includes live scrape progress) ───────────────── */}
      <div
        className="sticky top-0 z-10 space-y-2 border-b border-transparent pb-2"
        style={{ backgroundColor: 'var(--oc-bg)' }}
      >
        {/* Header — mobile-first: stack title, full-width search, then prompt link */}
        <div
          className="rounded-xl px-3 py-2.5"
          style={{ borderLeft: '3px solid var(--s1)', backgroundColor: 'var(--s1-bg)' }}
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-2">
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-bold" style={{ color: 'var(--s1-text)' }}>S1 · Scraping</h2>
              <p className="text-xs" style={{ color: 'var(--s1-text)', opacity: 0.7 }}>
                Web content extraction · {companies != null ? `${displayCount.toLocaleString()} companies` : '—'}
              </p>
            </div>
            <div className="flex min-w-0 w-full flex-col gap-2 sm:w-auto sm:shrink-0 sm:flex-row sm:items-center">
              <div className="relative min-w-0 w-full sm:w-[180px] sm:shrink-0">
                <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <input type="text" value={search} onChange={(e) => onSearchChange(e.target.value)} disabled={isLoading}
                  placeholder="Search domains…"
                  className="w-full rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--s1) focus:bg-white disabled:cursor-not-allowed disabled:opacity-60" />
              </div>
              <button
                type="button"
                onClick={onOpenPromptLibrary}
                disabled={isLoading}
                title={selectedScrapePrompt ? `Prompt: ${selectedScrapePrompt.name}` : 'Open scrape prompt library'}
                className="min-w-0 w-full text-left text-xs text-(--oc-muted) underline underline-offset-2 transition hover:text-(--oc-text) disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:max-w-[min(20rem,45vw)] sm:shrink-0 sm:text-right"
              >
                <span className="block min-w-0 truncate sm:whitespace-nowrap">
                  {selectedScrapePrompt ? `Prompt: ${selectedScrapePrompt.name}` : 'Select prompt…'}
                </span>
              </button>
            </div>
          </div>
          {scrape && (hasActivity || (summaryCounts?.scrape_done ?? 0) > 0 || failedCount > 0) && (
            <div className="mt-2 flex items-center gap-3 border-t border-(--oc-border) pt-1.5 text-xs text-(--oc-muted)">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${hasActivity ? 'animate-pulse bg-amber-400' : 'bg-(--oc-border)'}`} />
              <span className="flex items-center gap-1">
                {(summaryCounts?.scrape_in_progress ?? 0) > 0 && <span className="text-amber-600"><strong>{summaryCounts!.scrape_in_progress.toLocaleString()}</strong> in progress ·</span>}
                {(summaryCounts?.scrape_done ?? 0) > 0 && <span className="text-emerald-600"><strong>{summaryCounts!.scrape_done.toLocaleString()}</strong> done</span>}
                {failedCount > 0 && <span className="text-red-500"> · <strong>{failedCount.toLocaleString()}</strong> failed</span>}
                {scrape.stuck_count > 0 && (
                  <button type="button" onClick={onResetStuck} disabled={isLoading || isResettingStuck}
                    className="ml-2 text-rose-500 underline underline-offset-2 transition hover:text-rose-700 disabled:opacity-50">
                    {isResettingStuck ? 'Resetting…' : `${scrape.stuck_count} stuck — reset`}
                  </button>
                )}
              </span>
              <div className="flex-1 h-1 overflow-hidden rounded-full bg-(--oc-border)">
                <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(pctDone, 100)}%`, backgroundColor: 'var(--s1)' }} />
              </div>
              <span className="tabular-nums shrink-0">
                {counts ? `${counts.scrape_done.toLocaleString()} / ${counts.total.toLocaleString()}` : `${scrape.succeeded ?? 0} / ${total.toLocaleString()}`}
              </span>
            </div>
          )}
        </div>

        {/* Letter strip */}
        <LetterStrip multiSelect activeLetters={activeLetters} counts={letterCounts} onToggle={onToggleLetter} onClear={onClearLetters} disabled={isLoading} />

        {/* Sub-filter chips + Pager */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1.5">
              {SUB_FILTERS.map((f) => (
                <button key={f.value} type="button" onClick={() => onScrapeSubFilterChange(f.value)} disabled={isLoading}
                  className={`rounded-full px-3 py-1 text-[11px] font-bold transition ${scrapeSubFilter === f.value ? 'text-white' : isLoading ? 'border border-(--oc-border) text-(--oc-border) cursor-not-allowed' : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s1) hover:text-(--s1-text)'}`}
                  style={scrapeSubFilter === f.value ? { backgroundColor: 'var(--s1)' } : {}}>
                  {f.label}
                </button>
              ))}
            </div>
            <Pager offset={offset} pageSize={pageSize} total={companies?.total ?? null} hasMore={companies?.has_more ?? false} onPrev={onPagePrev} onNext={onPageNext} onPageSizeChange={onPageSizeChange} disabled={isLoading} />
          </div>

        {/* Selection bar */}
        <SelectionBar
          stageColor="--s1"
          stageBg="--s1-bg"
          selectedCount={selectedIds.length}
          totalMatching={effectiveTotalMatching}
          activeLetters={activeLetters}
          onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
          isSelectingAll={isSelectingAll}
          onClear={onClearSelection}
          disabled={isLoading}
        >
          <button type="button" onClick={onScrapeSelected} disabled={isLoading || isScraping || selectedIds.length === 0}
            className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
            style={{ backgroundColor: 'var(--s1)' }}>
            {isScraping ? 'Queuing…' : 'Scrape Selected'}
          </button>
        </SelectionBar>
      </div>
      {/* ── / Sticky controls ─────────────────────────────────────────────── */}

      {/* Table */}
      <div className="oc-panel overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-(--oc-border) text-[10px] uppercase tracking-wider text-(--oc-muted)">
              <th className="w-8 p-3">
                <input
                  type="checkbox"
                  disabled={isLoading}
                  checked={allVisibleSelected}
                  ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                  onChange={() =>
                    onToggleAll(allVisibleSelected ? [] : visibleCompanies.map((c) => c.id))
                  }
                  className="cursor-pointer disabled:cursor-not-allowed"
                />
              </th>
              <SortableHeader label="Domain" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
              <SortableHeader label="Activity" field="last_activity" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
              <SortableHeader label="Scrape status" field="scrape_status" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
              <th className="p-3 text-left font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 8 }).map((_, i) => (
              <tr key={i} className="border-b border-(--oc-border)">
                <td className="p-3"><div className="oc-skeleton h-4 w-4 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-36 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-14 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-5 w-20 rounded-full" /></td>
                <td className="p-3"><div className="oc-skeleton h-6 w-16 rounded-lg" /></td>
              </tr>
            ))}
            {!isLoading && visibleCompanies.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-10 text-center">
                  {scrapeSubFilter === 'not-started' && companies != null ? (
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-emerald-700">All companies have been scraped ✓</p>
                      <p className="text-xs text-(--oc-muted)">Switch to "All" or "Done" to review results.</p>
                    </div>
                  ) : scrapeSubFilter === 'soft' ? (
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-(--oc-text)">No soft failures</p>
                      <p className="text-xs text-(--oc-muted)">All scrapes completed successfully.</p>
                    </div>
                  ) : (
                    <p className="text-sm text-(--oc-muted)">No companies match this filter.</p>
                  )}
                </td>
              </tr>
            )}
            {visibleCompanies.map((c) => (
              <PipelineStageCompanyTableRow
                key={c.id}
                company={c}
                selected={selectedSet.has(c.id)}
                checkboxDisabled={isLoading}
                onToggle={() => onToggleRow(c.id)}
                stageAccentVar="--s1"
                stageBgVar="--s1-bg"
              >
                <td className="p-3">
                  {c.latest_scrape_status ? (
                    <Badge className={scrapeBadgeClass(c.latest_scrape_status, c.latest_scrape_failure_reason)}>
                      {scrapeBadgeLabel(c.latest_scrape_status, c.latest_scrape_failure_reason)}
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
                      disabled={isLoading || !!actionState[c.id]}
                      title={(c.latest_scrape_status ?? '').toLowerCase() === 'site_unavailable'
                        ? 'Permanent failure marker exists. Retry will attempt recovery explicitly.'
                        : undefined}
                      className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s1) hover:text-(--s1-text) disabled:opacity-50"
                    >
                      {actionState[c.id] ?? 'Scrape'}
                    </button>
                    {c.latest_scrape_job_id && (
                      <button
                        type="button"
                        onClick={() => onOpenDiagnostics(c)}
                        disabled={isLoading}
                        className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s1) hover:text-(--s1-text) disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Diag
                      </button>
                    )}
                  </div>
                </td>
              </PipelineStageCompanyTableRow>
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
            disabled={isLoading || isDrainingQueue || stats.scrape.queued === 0}
            className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isDrainingQueue ? 'Draining…' : `Drain Queue (${stats.scrape.queued})`}
          </button>
        </div>
      )}
    </div>
  )
}
