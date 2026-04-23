import type { CompanyList, CompanyListItem, CostStatsResponse, PipelineCostSummaryRead, PipelineRunProgressRead } from '../../../lib/types'
import {
  companyListBrowseUrl,
  type FullPipelineStatusFilter,
} from '../../../lib/fullPipelineFilters'
import { getResumeStageForCompany } from '../../../lib/pipelineMappings'
import { LetterStrip } from '../../ui/LetterStrip'
import { Pager } from '../../ui/Pager'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'
import { SelectionBar } from '../../ui/SelectionBar'
import { SortableHeader } from '../../ui/SortableHeader'

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
  if (s === 'site_unavailable') return { label: 'Permanent fail', variant: 'err' }
  if (s === 'failed' || s === 'step1_failed') return { label: 'Soft fail', variant: 'warn' }
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

// Status filter semantics: see `fullPipelineFilters.ts` (shared with select-all-matching).

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

const STATUS_FILTERS: Array<{ value: FullPipelineStatusFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'not-started', label: 'Not started' },
  { value: 'in-progress', label: 'In progress' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'complete', label: 'Complete' },
  { value: 'permanent-failures', label: 'Permanent fail' },
  { value: 'soft-failures', label: 'Soft fail' },
]

// ── Props ─────────────────────────────────────────────────────────────────────

interface FullPipelineViewProps {
  activeCampaignName: string | null
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetter: string | null
  selectedIds: string[]
  resumeActionState: Record<string, string>
  isLoading: boolean
  offset: number
  pageSize: number
  statusFilter: FullPipelineStatusFilter
  search: string
  onLetterChange: (l: string | null) => void
  onStatusFilterChange: (filter: FullPipelineStatusFilter) => void
  onSearchChange: (value: string) => void
  onToggleRow: (id: string) => void
  onToggleAll: (ids: string[]) => void
  onClearSelection: () => void
  onScrapeSelected: () => void
  onStartCampaignPipeline: () => void
  onResumeCompany: (company: CompanyListItem) => void
  isScraping: boolean
  isStartingCampaignPipeline: boolean
  onPagePrev: () => void
  onPageNext: () => void
  onPageSizeChange: (size: number) => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
  isSelectingAllMatching: boolean
  onSelectAllMatching: () => void
  latestRunProgress: PipelineRunProgressRead | null
  campaignCostSummary: PipelineCostSummaryRead | null
  campaignCostBreakdown: CostStatsResponse | null
}

// ── Component ─────────────────────────────────────────────────────────────────

export function FullPipelineView({
  activeCampaignName,
  companies,
  letterCounts,
  activeLetter,
  selectedIds,
  resumeActionState,
  isLoading,
  offset,
  pageSize,
  statusFilter,
  search,
  onLetterChange,
  onStatusFilterChange,
  onSearchChange,
  onToggleRow,
  onToggleAll,
  onClearSelection,
  onScrapeSelected,
  onStartCampaignPipeline,
  onResumeCompany,
  isScraping,
  isStartingCampaignPipeline,
  onPagePrev,
  onPageNext,
  onPageSizeChange,
  sortBy,
  sortDir,
  onSort,
  isSelectingAllMatching,
  onSelectAllMatching,
  latestRunProgress,
  campaignCostSummary,
  campaignCostBreakdown,
}: FullPipelineViewProps) {
  const selectedSet = new Set(selectedIds)
  const visibleCompanies = companies?.items ?? []

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-0 overflow-hidden">
      {/* Top controls — sticky within page scroll on small layouts; fixed strip when column fills viewport */}
      <div
        className="sticky top-0 z-20 shrink-0 space-y-2 border-b border-(--oc-border) bg-(--oc-bg)/95 pb-2 backdrop-blur-sm"
      >
      <p className="px-1 pt-1 text-[11px] text-(--oc-muted)">
        Cross-stage control center. For detailed stage work, use the dedicated S1-S4 views.
      </p>
      {/* Topbar */}
      <div className="flex items-center gap-2 px-1 pt-1">
        <span className="text-sm font-extrabold tracking-tight text-(--oc-accent-ink)">
          Full Pipeline
        </span>
        {activeCampaignName && (
          <span className="rounded-full border border-(--oc-border) bg-white px-2 py-0.5 text-[11px] font-semibold text-(--oc-muted)">
            {activeCampaignName}
          </span>
        )}
        {companies?.total != null && (
          <span className="text-xs text-(--oc-muted)">{companies.total.toLocaleString()} domains</span>
        )}
        <div className="relative ml-1 flex-1 max-w-72">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            disabled={isLoading}
            placeholder="Search domains…"
            className="w-full rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--oc-accent) focus:bg-white disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>
        <button
          type="button"
          onClick={onStartCampaignPipeline}
          disabled={isLoading || isStartingCampaignPipeline}
          title="Starts a chained campaign pipeline run (S1→S4)."
          className="rounded-lg border border-(--oc-accent) bg-(--oc-accent-soft) px-3 py-1.5 text-xs font-semibold text-(--oc-accent-ink) transition hover:bg-(--oc-accent-soft)/80 disabled:opacity-60"
        >
          {isStartingCampaignPipeline ? 'Starting run…' : 'Start campaign pipeline'}
        </button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 px-1 pb-1">
        <LetterStrip
          active={activeLetter}
          onChange={onLetterChange}
          counts={letterCounts}
          disabled={isLoading}
        />
        <span className="h-5 w-px bg-(--oc-border)" />
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => onStatusFilterChange(f.value)}
              disabled={isLoading}
              className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                statusFilter === f.value
                  ? 'border border-(--oc-accent) bg-(--oc-accent-soft) text-(--oc-accent-ink)'
                  : isLoading
                    ? 'border border-(--oc-border) bg-white text-(--oc-border) cursor-not-allowed'
                    : 'border border-(--oc-border) bg-white text-(--oc-muted) hover:border-(--oc-accent) hover:text-(--oc-accent-ink)'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="h-5 w-px bg-(--oc-border)" />
        <Pager
          offset={offset}
          pageSize={pageSize}
          total={companies?.total ?? null}
          hasMore={companies?.has_more ?? false}
          onPrev={onPagePrev}
          onNext={onPageNext}
          onPageSizeChange={onPageSizeChange}
          disabled={isLoading}
        />
        <button
          type="button"
          disabled={isLoading || isSelectingAllMatching}
          onClick={onSelectAllMatching}
          className="rounded-full border border-(--oc-border) bg-white px-3 py-1 text-[11px] font-semibold text-(--oc-accent-ink) transition hover:border-(--oc-accent) disabled:opacity-50"
        >
          {isSelectingAllMatching ? 'Selecting…' : 'Select all matching filters'}
        </button>
        {campaignCostSummary && (
          <span className="rounded-full border border-(--oc-border) bg-white px-3 py-1 text-[11px] font-semibold text-(--oc-muted)">
            Campaign spend: ${Number(campaignCostSummary.total_cost_usd || 0).toFixed(4)}
          </span>
        )}
        {campaignCostBreakdown && (
          <span className="rounded-full border border-(--oc-border) bg-white px-3 py-1 text-[11px] font-semibold text-(--oc-muted)">
            Domains with spend: {campaignCostBreakdown.total}
          </span>
        )}
      </div>
      {latestRunProgress && (
        <div className="space-y-2 rounded-lg border border-(--oc-border) bg-white px-3 py-2">
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <span className="font-semibold text-(--oc-text)">
              Live run status: {latestRunProgress.status}
            </span>
            <span className="text-(--oc-muted)">
              queued {latestRunProgress.queued_count} · reused {latestRunProgress.reused_count} · failed {latestRunProgress.failed_count}
            </span>
          </div>
          {Object.entries(latestRunProgress.stages).map(([stage, counts]) => {
            const total = Math.max(1, counts.total)
            const done = counts.completed + counts.failed
            const pct = Math.min(100, Math.round((done / total) * 100))
            return (
              <div key={stage} className="space-y-1">
                <div className="flex items-center justify-between text-[10px] text-(--oc-muted)">
                  <span>{stage}</span>
                  <span>
                    {counts.running} running · {counts.completed} done · {counts.failed} failed
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-(--oc-surface)">
                  <div className="h-full rounded-full bg-(--oc-accent)" style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
      </div>

      {/* Selection bar */}
      <SelectionBar
        stageColor="--oc-accent"
        stageBg="--oc-accent-soft"
        selectedCount={selectedIds.length}
        totalMatching={companies?.total ?? null}
        activeLetters={activeLetter ? new Set([activeLetter]) : new Set()}
        onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
        isSelectingAll={isSelectingAllMatching}
        onClear={onClearSelection}
        disabled={isLoading}
      >
        <button
          type="button"
          onClick={onScrapeSelected}
          disabled={isLoading || isScraping || selectedIds.length === 0}
          title="Starts a chained run for selected rows (S1→S4)."
          className="rounded-lg bg-(--oc-accent) px-3 py-1.5 text-xs font-bold text-white transition hover:opacity-90 disabled:opacity-60"
        >
          {isScraping ? 'Starting run…' : 'Start pipeline'}
        </button>
      </SelectionBar>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <div className="min-w-180">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-(--oc-border) bg-white/95 backdrop-blur-sm">
                <th className="w-10 p-3 pl-4">
                  <input
                    type="checkbox"
                    disabled={isLoading}
                    checked={allVisibleSelected}
                    ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                    onChange={() => onToggleAll(allVisibleSelected ? [] : visibleCompanies.map((c) => c.id))}
                    className="cursor-pointer accent-(--oc-accent) disabled:cursor-not-allowed"
                  />
                </th>
                <th className="min-w-52 p-3 text-left text-[10.5px] font-bold uppercase tracking-widest text-(--oc-muted)">
                  Domain
                </th>
                <SortableHeader
                  label="Last activity"
                  field="last_activity"
                  sortBy={sortBy}
                  sortDir={sortDir}
                  onSort={onSort}
                  className="min-w-28 text-[10.5px] font-bold uppercase tracking-widest text-(--oc-muted)"
                  disabled={isLoading}
                />
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
                <th className="min-w-32 p-3 text-left text-[10.5px] font-bold uppercase tracking-widest text-(--oc-muted)">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={8} className="p-8 text-center text-sm text-(--oc-muted)">Loading…</td>
                </tr>
              )}
              {!isLoading && visibleCompanies.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-8 text-center text-sm text-(--oc-muted)">
                    No companies match this filter.
                  </td>
                </tr>
              )}
              {visibleCompanies.map((c) => {
                const isSelected = selectedSet.has(c.id)
                const resumeStage = getResumeStageForCompany(c)
                const resumeLabel = resumeActionState[c.id]
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
                        disabled={isLoading}
                        checked={isSelected}
                        onChange={() => onToggleRow(c.id)}
                        className="cursor-pointer accent-(--oc-accent) disabled:cursor-not-allowed"
                      />
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-(--oc-border) bg-(--oc-surface) text-[11px] font-bold text-(--oc-accent-ink)">
                          {c.domain[0].toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <a
                            href={companyListBrowseUrl(c)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block truncate font-mono text-xs font-medium text-(--oc-accent-ink) hover:underline"
                          >
                            {c.domain}
                          </a>
                          <p className="text-[10.5px] text-(--oc-muted)">
                            Added {new Date(c.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="p-3 text-[11px] text-(--oc-muted) tabular-nums">
                      <RelativeTimeLabel timestamp={c.last_activity} prefix="" />
                    </td>
                    <td className="p-3"><StatusBadge {...s1Status(c)} /></td>
                    <td className="p-3"><StatusBadge {...s2Status(c)} /></td>
                    <td className="p-3"><StatusBadge {...s3Status(c)} /></td>
                    <td className="p-3"><StatusBadge {...s4Status(c)} /></td>
                    <td className="p-3">
                      {resumeStage ? (
                        <button
                          type="button"
                          onClick={() => onResumeCompany(c)}
                          disabled={isLoading || Boolean(resumeLabel)}
                          className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-semibold transition hover:border-(--oc-accent) hover:text-(--oc-accent-ink) disabled:opacity-50"
                        >
                          {resumeLabel ?? `Resume ${resumeStage}`}
                        </button>
                      ) : (
                        <span className="text-[11px] text-(--oc-muted)">—</span>
                      )}
                    </td>
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
            Showing {visibleCompanies.length.toLocaleString()} on this page
          </span>
          {companies.has_more && (
            <span className="text-xs text-(--oc-accent)">Scroll or adjust letter filter to see more</span>
          )}
        </div>
      )}
    </div>
  )
}
