import { useState } from 'react'
import type { CompanyList, CompanyListItem, StatsResponse } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'

type ScrapeSubFilter = 'all' | 'pending' | 'active' | 'done' | 'failed'

interface S1ScrapingViewProps {
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  selectedIds: string[]
  totalMatching: number | null
  isLoading: boolean
  isScraping: boolean
  isSelectingAll: boolean
  stats: StatsResponse | null
  isResettingStuck: boolean
  isDrainingQueue: boolean
  actionState: Record<string, string>
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
  if (s === 'succeeded' || s === 'completed') return 'bg-emerald-50 text-emerald-800'
  if (s === 'running') return 'bg-blue-50 text-blue-800'
  if (s === 'queued') return 'bg-amber-50 text-amber-800'
  if (s === 'failed' || s === 'dead') return 'bg-rose-50 text-rose-800'
  return 'bg-slate-100 text-slate-600'
}

export function S1ScrapingView({
  companies,
  letterCounts,
  activeLetters,
  selectedIds,
  totalMatching,
  isLoading,
  isScraping,
  isSelectingAll,
  stats,
  isResettingStuck,
  isDrainingQueue,
  actionState,
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
}: S1ScrapingViewProps) {
  const [subFilter, setSubFilter] = useState<ScrapeSubFilter>('pending')
  const selectedSet = new Set(selectedIds)

  const visibleCompanies = (companies?.items ?? []).filter((c) => {
    const letterOk = activeLetters.size === 0 || activeLetters.has(c.domain[0].toLowerCase())
    if (!letterOk) return false
    if (subFilter === 'pending') return !c.latest_scrape_status || c.latest_scrape_status === 'none'
    if (subFilter === 'active') return c.latest_scrape_status === 'queued' || c.latest_scrape_status === 'running'
    if (subFilter === 'done') return !!c.latest_scrape_terminal && c.latest_scrape_status !== 'failed' && c.latest_scrape_status !== 'dead'
    if (subFilter === 'failed') return c.latest_scrape_status === 'failed' || c.latest_scrape_status === 'dead'
    return true
  })

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold" style={{ color: 'var(--s1-text)' }}>S1 · Scraping</h2>
          <p className="text-xs text-(--oc-muted)">
            Web content extraction · {companies?.total != null ? `${companies.total.toLocaleString()} companies` : '—'}
          </p>
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
            onClick={() => setSubFilter(f.value)}
            className={`rounded-full px-3 py-1 text-[11px] font-bold transition ${
              subFilter === f.value
                ? 'text-white'
                : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s1) hover:text-(--s1-text)'
            }`}
            style={subFilter === f.value ? { backgroundColor: 'var(--s1)' } : {}}
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
        totalMatching={totalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
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
            <tr className="border-b border-(--oc-border) text-xs text-(--oc-muted)">
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
              <th className="p-3 text-left font-semibold">Domain</th>
              <th className="p-3 text-left font-semibold">Scrape status</th>
              <th className="p-3 text-left font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={4} className="p-6 text-center text-(--oc-muted)">Loading…</td></tr>
            )}
            {!isLoading && visibleCompanies.length === 0 && (
              <tr><td colSpan={4} className="p-6 text-center text-(--oc-muted)">No companies match this filter.</td></tr>
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
                    href={c.raw_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium hover:underline"
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
                      className="rounded-lg border border-(--oc-border) px-2 py-1 text-[11px] font-medium transition hover:border-(--s1) hover:text-(--s1-text) disabled:opacity-50"
                    >
                      {actionState[c.id] ?? 'Scrape'}
                    </button>
                    {c.latest_scrape_job_id && (
                      <button
                        type="button"
                        onClick={() => onOpenDiagnostics(c)}
                        className="rounded-lg border border-(--oc-border) px-2 py-1 text-[11px] font-medium transition hover:border-(--s1) hover:text-(--s1-text)"
                      >
                        Diagnostics
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pipeline operations panel */}
      {stats && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-(--oc-border) bg-white p-3">
          <p className="mr-2 text-xs font-bold text-(--oc-muted)">Pipeline ops</p>
          <button
            type="button"
            onClick={onResetStuck}
            disabled={isResettingStuck || stats.scrape.stuck_count === 0}
            className="rounded-lg border border-(--oc-border) px-3 py-1.5 text-xs font-bold transition hover:border-(--oc-accent) hover:text-(--oc-accent-ink) disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isResettingStuck ? 'Resetting…' : `Reset Stuck (${stats.scrape.stuck_count})`}
          </button>
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
