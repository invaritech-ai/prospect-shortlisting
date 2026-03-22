import { useEffect, useRef, useState } from 'react'
import type { ScrapeJobRead } from '../../lib/types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { SkeletonTable } from '../ui/Skeleton'
import {
  IconChevronLeft,
  IconChevronRight,
  IconRefresh,
  IconEye,
  IconGlobe,
  IconExternalLink,
} from '../ui/icons'

type JobFilter = 'all' | 'active' | 'completed' | 'failed'
type SortField = 'updated_at' | 'domain' | 'pages' | 'failures'
type SortDir = 'asc' | 'desc'

const JOB_FILTERS: Array<{ value: JobFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

const SORT_OPTIONS: Array<{ value: SortField; label: string }> = [
  { value: 'updated_at', label: 'Updated' },
  { value: 'domain', label: 'Domain' },
  { value: 'pages', label: 'Pages' },
  { value: 'failures', label: 'Failures' },
]

const GROUP_LABELS: Record<string, string> = {
  Active: 'Active',
  Done: 'Done',
  Failed: 'Failed',
  Unavailable: 'Unavailable',
}

const GROUP_ORDER = ['Active', 'Failed', 'Done', 'Unavailable']

interface ScrapeJobsViewProps {
  scrapeJobs: ScrapeJobRead[]
  isLoading: boolean
  jobsOffset: number
  jobsPageSize: number
  jobsFilter: JobFilter
  jobsSearch: string
  jobsHasMore: boolean
  onSetJobsFilter: (f: JobFilter) => void
  onSetJobsSearch: (s: string) => void
  onSetJobsPageSize: (n: number) => void
  onPagePrev: () => void
  onPageNext: () => void
  onRefresh: () => void
  onViewMarkdown: (job: ScrapeJobRead) => void
}

function badgeForJob(job: ScrapeJobRead): { variant: 'info' | 'success' | 'fail' | 'neutral'; label: string } {
  if (!job.terminal_state) {
    return { variant: 'info', label: job.status === 'running' ? 'Running' : 'Queued' }
  }
  if (job.status === 'site_unavailable') return { variant: 'neutral', label: 'Unavailable' }
  if (job.status === 'failed' || job.status.includes('failed') || !!job.last_error_code) {
    return { variant: 'fail', label: 'Failed' }
  }
  return { variant: 'success', label: 'Done' }
}

function groupLabel(job: ScrapeJobRead): string {
  const badge = badgeForJob(job)
  if (badge.variant === 'info') return 'Active'
  if (badge.variant === 'success') return 'Done'
  if (badge.variant === 'fail') return 'Failed'
  return 'Unavailable'
}

function sortJobs(jobs: ScrapeJobRead[], field: SortField, dir: SortDir): ScrapeJobRead[] {
  return [...jobs].sort((a, b) => {
    let cmp = 0
    switch (field) {
      case 'updated_at': cmp = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime(); break
      case 'domain': cmp = a.domain.localeCompare(b.domain); break
      case 'pages': cmp = a.pages_fetched_count - b.pages_fetched_count; break
      case 'failures': cmp = a.fetch_failures_count - b.fetch_failures_count; break
    }
    return dir === 'asc' ? cmp : -cmp
  })
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

function MiniProgress({ fetched, total, markdown, active }: {
  fetched: number; total: number; markdown: number; active: boolean
}) {
  if (fetched === 0 && total === 0) return <span className="text-(--oc-border)">—</span>
  const pct = total > 0 ? Math.min(100, Math.round((fetched / total) * 100)) : 100
  return (
    <div className="space-y-1 min-w-20">
      <div className="h-1 w-20 rounded-full bg-(--oc-border) overflow-hidden">
        <div
          className={`h-full rounded-full bg-(--oc-accent) transition-all duration-500${active ? ' animate-pulse' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[11px] tabular-nums text-(--oc-muted) leading-tight">
        <span className="font-medium text-(--oc-text)">{fetched}</span>
        {total > 0 && <span className="text-(--oc-border)">/{total}</span>}
        {' '}<span className="text-(--oc-border)">·</span>{' '}
        <span className={markdown > 0 ? 'text-(--oc-accent-ink) font-medium' : 'text-(--oc-border)'}>
          {markdown} md
        </span>
      </p>
    </div>
  )
}

function IssueCell({ failures, errorCode }: { failures: number; errorCode: string | null }) {
  if (failures === 0 && !errorCode) return <span className="text-(--oc-border)">—</span>
  return (
    <div className="space-y-1">
      {failures > 0 && (
        <span className="inline-flex items-center rounded-md bg-orange-50 px-1.5 py-0.5 text-[11px] font-semibold text-orange-700 ring-1 ring-inset ring-orange-200">
          {failures} fail{failures !== 1 ? 's' : ''}
        </span>
      )}
      {errorCode && (
        <p className="text-[11px] text-(--oc-fail-text) font-mono leading-tight truncate max-w-35" title={errorCode}>
          {errorCode}
        </p>
      )}
    </div>
  )
}

function RunningDot() {
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-(--oc-accent) opacity-60" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-(--oc-accent)" />
    </span>
  )
}

function GroupHeader({ label, count }: { label: string; count: number }) {
  const colors: Record<string, string> = {
    Active: 'text-blue-700 bg-blue-50 ring-blue-200',
    Done: 'text-emerald-700 bg-emerald-50 ring-emerald-200',
    Failed: 'text-red-700 bg-red-50 ring-red-200',
    Unavailable: 'text-slate-600 bg-slate-50 ring-slate-200',
  }
  return (
    <tr className="bg-(--oc-accent-soft)/5">
      <td colSpan={6} className="py-1.5 px-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold uppercase tracking-widest text-(--oc-muted)">{GROUP_LABELS[label] ?? label}</span>
          <span className={`inline-flex items-center rounded-full px-1.5 py-0 text-[10px] font-bold ring-1 ring-inset ${colors[label] ?? 'text-slate-600 bg-slate-50 ring-slate-200'}`}>
            {count}
          </span>
        </div>
      </td>
    </tr>
  )
}

function JobRow({ job, onViewMarkdown }: { job: ScrapeJobRead; onViewMarkdown: () => void }) {
  const badge = badgeForJob(job)
  const active = !job.terminal_state
  return (
    <tr className={active ? 'bg-(--oc-accent-soft)/10' : ''}>
      <td>
        <div className="flex items-center gap-1.5">
          {active && <RunningDot />}
          <div className="min-w-0">
            <a
              href={job.normalized_url || `https://${job.domain}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 font-semibold text-(--oc-accent-ink) hover:underline max-w-50 truncate"
              title={job.normalized_url}
            >
              {job.domain}
              <IconExternalLink size={11} className="shrink-0 opacity-40" />
            </a>
            <p className="font-mono text-[10px] text-(--oc-muted) leading-tight mt-0.5">{job.id.slice(0, 8)}…</p>
          </div>
        </div>
      </td>
      <td><Badge variant={badge.variant}>{badge.label}</Badge></td>
      <td>
        <MiniProgress
          fetched={job.pages_fetched_count}
          total={job.discovered_urls_count}
          markdown={job.markdown_pages_count}
          active={active}
        />
      </td>
      <td><IssueCell failures={job.fetch_failures_count} errorCode={job.last_error_code} /></td>
      <td className="text-[12px] text-(--oc-muted) whitespace-nowrap" title={new Date(job.updated_at).toLocaleString()}>
        {relativeTime(job.updated_at)}
      </td>
      <td>
        {job.markdown_pages_count > 0 && (
          <Button variant="secondary" size="xs" onClick={onViewMarkdown}>
            <IconEye size={13} />
            View
          </Button>
        )}
      </td>
    </tr>
  )
}

function JobCard({ job, onViewMarkdown }: { job: ScrapeJobRead; onViewMarkdown: () => void }) {
  const badge = badgeForJob(job)
  const active = !job.terminal_state
  return (
    <div className={`rounded-2xl border bg-white p-3.5 transition-colors ${active ? 'border-(--oc-accent)/30 bg-(--oc-accent-soft)/20' : 'border-(--oc-border)'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex items-center gap-2">
          {active && <RunningDot />}
          <div className="min-w-0">
            <a
              href={job.normalized_url || `https://${job.domain}`}
              target="_blank"
              rel="noreferrer"
              className="truncate block font-semibold text-(--oc-accent-ink) hover:underline"
            >
              {job.domain}
            </a>
            <p className="mt-0.5 font-mono text-[10px] text-(--oc-muted)">{job.id.slice(0, 8)}…</p>
          </div>
        </div>
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>
      <div className="mt-3 flex items-center gap-4">
        <MiniProgress
          fetched={job.pages_fetched_count}
          total={job.discovered_urls_count}
          markdown={job.markdown_pages_count}
          active={active}
        />
        {(job.fetch_failures_count > 0 || job.last_error_code) && (
          <IssueCell failures={job.fetch_failures_count} errorCode={job.last_error_code} />
        )}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2">
        <span className="text-[11px] text-(--oc-muted)" title={new Date(job.updated_at).toLocaleString()}>
          {relativeTime(job.updated_at)}
        </span>
        {job.markdown_pages_count > 0 && (
          <Button variant="secondary" size="xs" onClick={onViewMarkdown}>
            <IconEye size={13} />
            View Markdown
          </Button>
        )}
      </div>
    </div>
  )
}

export function ScrapeJobsView({
  scrapeJobs,
  isLoading,
  jobsOffset,
  jobsPageSize,
  jobsFilter,
  jobsSearch,
  jobsHasMore,
  onSetJobsFilter,
  onSetJobsSearch,
  onSetJobsPageSize,
  onPagePrev,
  onPageNext,
  onRefresh,
  onViewMarkdown,
}: ScrapeJobsViewProps) {
  const rangeLabel = scrapeJobs.length > 0 ? `${jobsOffset + 1}–${jobsOffset + scrapeJobs.length}` : '0'
  const canPrev = jobsOffset > 0 && !isLoading
  const canNext = jobsHasMore && !isLoading

  // Local search input (debounced up to parent)
  const [localSearch, setLocalSearch] = useState(jobsSearch)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => { setLocalSearch(jobsSearch) }, [jobsSearch])

  function handleSearchChange(val: string) {
    setLocalSearch(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => onSetJobsSearch(val), 350)
  }

  // Sort + group (client-side, applied to loaded page)
  const [sortField, setSortField] = useState<SortField>('updated_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [groupBy, setGroupBy] = useState(false)

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('desc') }
  }

  const sorted = sortJobs(scrapeJobs, sortField, sortDir)

  // Build groups: { Active: [...], Done: [...], Failed: [...], Unavailable: [...] }
  const groups = sorted.reduce<Record<string, ScrapeJobRead[]>>((acc, job) => {
    const g = groupLabel(job)
    ;(acc[g] ??= []).push(job)
    return acc
  }, {})

  const sortIcon = (field: SortField) => {
    if (sortField !== field) return <span className="text-(--oc-border) ml-0.5">↕</span>
    return <span className="text-(--oc-accent) ml-0.5">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="oc-toolbar space-y-3">
        {/* Row 1: title + refresh + rows */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold tracking-tight md:text-lg">Scrape Jobs</h2>
            <p className="hidden text-xs text-(--oc-muted) sm:block">Active jobs auto-refresh every 4s</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onRefresh} loading={isLoading}>
              <IconRefresh size={15} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <label className="flex items-center gap-1.5 text-[11px] font-semibold text-(--oc-muted)">
              Rows
              <select
                value={jobsPageSize}
                onChange={(e) => onSetJobsPageSize(Number(e.target.value))}
                className="rounded-lg border border-(--oc-border) bg-white px-2 py-1 text-xs font-semibold text-(--oc-text)"
              >
                {PAGE_SIZE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          </div>
        </div>

        {/* Row 2: search + sort + group */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 min-w-40">
            <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            <input
              type="search"
              placeholder="Search domains…"
              value={localSearch}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="w-full rounded-lg border border-(--oc-border) bg-white pl-8 pr-3 py-1.5 text-xs text-(--oc-text) placeholder:text-(--oc-muted) focus:border-(--oc-accent) focus:outline-none focus:ring-1 focus:ring-(--oc-accent)"
            />
          </div>

          {/* Sort */}
          <label className="flex items-center gap-1.5 text-[11px] font-semibold text-(--oc-muted) shrink-0">
            Sort
            <select
              value={sortField}
              onChange={(e) => setSortField(e.target.value as SortField)}
              className="rounded-lg border border-(--oc-border) bg-white px-2 py-1 text-xs font-semibold text-(--oc-text)"
            >
              {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button
              type="button"
              onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}
              title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
              className="flex h-6 w-6 items-center justify-center rounded-md border border-(--oc-border) bg-white text-xs text-(--oc-text) hover:bg-(--oc-accent-soft) transition"
            >
              {sortDir === 'asc' ? '↑' : '↓'}
            </button>
          </label>

          {/* Group toggle */}
          <button
            type="button"
            onClick={() => setGroupBy(g => !g)}
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-bold transition shrink-0 ${
              groupBy
                ? 'border-(--oc-accent) bg-(--oc-accent-soft) text-(--oc-accent-ink)'
                : 'border-(--oc-border) bg-white text-(--oc-muted) hover:text-(--oc-text)'
            }`}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
            </svg>
            Group
          </button>
        </div>

        {/* Row 3: status filters + pager */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {JOB_FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => onSetJobsFilter(item.value)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  jobsFilter === item.value
                    ? 'bg-(--oc-accent) text-white'
                    : 'border border-(--oc-border) bg-white text-(--oc-muted) hover:text-(--oc-text)'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onPagePrev}
              disabled={!canPrev}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-(--oc-border) bg-white text-(--oc-text) transition hover:bg-(--oc-accent-soft) disabled:cursor-not-allowed disabled:opacity-40"
            >
              <IconChevronLeft size={16} />
            </button>
            <span className="oc-kbd">{rangeLabel}</span>
            <button
              type="button"
              onClick={onPageNext}
              disabled={!canNext}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-(--oc-border) bg-white text-(--oc-text) transition hover:bg-(--oc-accent-soft) disabled:cursor-not-allowed disabled:opacity-40"
            >
              <IconChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      {isLoading && scrapeJobs.length === 0 ? (
        <SkeletonTable rows={6} />
      ) : scrapeJobs.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-(--oc-border) py-16 text-center">
          <IconGlobe size={36} className="mb-3 text-(--oc-border)" />
          <p className="font-semibold text-(--oc-accent-ink)">No scrape jobs</p>
          <p className="mt-1 text-sm text-(--oc-muted)">
            {localSearch ? `No results for "${localSearch}".` : jobsFilter !== 'all' ? 'Try switching to "All" to see all jobs.' : 'Trigger a scrape from the Companies view.'}
          </p>
        </div>
      ) : (
        <>
          {/* Mobile cards */}
          <div className="space-y-2 md:hidden">
            {groupBy ? (
              GROUP_ORDER.filter(g => groups[g]?.length).map(g => (
                <div key={g}>
                  <p className="mb-1.5 text-[11px] font-bold uppercase tracking-widest text-(--oc-muted) px-1">{g} · {groups[g].length}</p>
                  <div className="space-y-2">
                    {groups[g].map(job => <JobCard key={job.id} job={job} onViewMarkdown={() => onViewMarkdown(job)} />)}
                  </div>
                </div>
              ))
            ) : (
              sorted.map(job => <JobCard key={job.id} job={job} onViewMarkdown={() => onViewMarkdown(job)} />)
            )}
          </div>

          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto rounded-2xl border border-(--oc-border) bg-white">
            <table className="oc-compact-table min-w-175">
              <thead>
                <tr>
                  <th>
                    <button type="button" onClick={() => toggleSort('domain')} className="flex items-center gap-0.5 font-semibold hover:text-(--oc-text) transition">
                      Domain{sortIcon('domain')}
                    </button>
                  </th>
                  <th>Status</th>
                  <th>
                    <button type="button" onClick={() => toggleSort('pages')} className="flex items-center gap-0.5 font-semibold hover:text-(--oc-text) transition">
                      Progress{sortIcon('pages')}
                    </button>
                  </th>
                  <th>
                    <button type="button" onClick={() => toggleSort('failures')} className="flex items-center gap-0.5 font-semibold hover:text-(--oc-text) transition">
                      Issues{sortIcon('failures')}
                    </button>
                  </th>
                  <th>
                    <button type="button" onClick={() => toggleSort('updated_at')} className="flex items-center gap-0.5 font-semibold hover:text-(--oc-text) transition">
                      Updated{sortIcon('updated_at')}
                    </button>
                  </th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {groupBy ? (
                  GROUP_ORDER.filter(g => groups[g]?.length).flatMap(g => [
                    <GroupHeader key={`gh-${g}`} label={g} count={groups[g].length} />,
                    ...groups[g].map(job => (
                      <JobRow key={job.id} job={job} onViewMarkdown={() => onViewMarkdown(job)} />
                    )),
                  ])
                ) : (
                  sorted.map(job => <JobRow key={job.id} job={job} onViewMarkdown={() => onViewMarkdown(job)} />)
                )}
              </tbody>
            </table>
          </div>

          {/* Bottom pager */}
          <div className="flex justify-end gap-1.5">
            <button
              type="button"
              onClick={onPagePrev}
              disabled={!canPrev}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-(--oc-border) bg-white transition hover:bg-(--oc-accent-soft) disabled:cursor-not-allowed disabled:opacity-40"
            >
              <IconChevronLeft size={16} />
            </button>
            <span className="oc-kbd">{rangeLabel}</span>
            <button
              type="button"
              onClick={onPageNext}
              disabled={!canNext}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-(--oc-border) bg-white transition hover:bg-(--oc-accent-soft) disabled:cursor-not-allowed disabled:opacity-40"
            >
              <IconChevronRight size={16} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
