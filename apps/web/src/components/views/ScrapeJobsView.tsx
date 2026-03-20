import type { ScrapeJobRead } from '../../lib/types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { SkeletonTable } from '../ui/Skeleton'
import { IconChevronLeft, IconChevronRight, IconRefresh, IconEye, IconGlobe } from '../ui/icons'

type JobFilter = 'all' | 'active' | 'completed' | 'failed'

const JOB_FILTERS: Array<{ value: JobFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

interface ScrapeJobsViewProps {
  scrapeJobs: ScrapeJobRead[]
  isLoading: boolean
  jobsOffset: number
  jobsPageSize: number
  jobsFilter: JobFilter
  jobsHasMore: boolean
  onSetJobsFilter: (f: JobFilter) => void
  onSetJobsPageSize: (n: number) => void
  onPagePrev: () => void
  onPageNext: () => void
  onRefresh: () => void
  onViewMarkdown: (job: ScrapeJobRead) => void
}

function badgeForJob(job: ScrapeJobRead): { variant: 'info' | 'success' | 'fail' | 'neutral'; label: string } {
  if (!job.terminal_state) {
    const label = job.stage2_status === 'running' ? 'Stage 2' : job.stage1_status === 'running' ? 'Stage 1' : job.status
    return { variant: 'info', label }
  }
  if (job.status === 'site_unavailable') {
    return { variant: 'neutral', label: 'Site Down' }
  }
  if (job.status.includes('failed') || job.stage1_status === 'failed' || job.stage2_status === 'failed' || !!job.last_error_code) {
    return { variant: 'fail', label: 'Failed' }
  }
  return { variant: 'success', label: 'Done' }
}

function JobCard({ job, onViewMarkdown }: { job: ScrapeJobRead; onViewMarkdown: () => void }) {
  const badge = badgeForJob(job)
  return (
    <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <a
            href={job.normalized_url || `https://${job.domain}`}
            target="_blank"
            rel="noreferrer"
            className="truncate block font-semibold text-[var(--oc-accent-ink)] hover:underline"
          >
            {job.domain}
          </a>
          <p className="mt-0.5 font-mono text-[10px] text-[var(--oc-muted)]">{job.id.slice(0, 8)}…</p>
        </div>
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--oc-muted)]">
        <span>Stage 1: {job.stage1_status}</span>
        <span>Stage 2: {job.stage2_status}</span>
        {job.pages_fetched_count > 0 && (
          <span>{job.markdown_pages_count}/{job.pages_fetched_count} pages</span>
        )}
        {job.last_error_code && (
          <span className="text-[var(--oc-fail-text)]">{job.last_error_code}</span>
        )}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2">
        <span className="text-[11px] text-[var(--oc-muted)]">
          {new Date(job.updated_at).toLocaleString()}
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
  jobsHasMore,
  onSetJobsFilter,
  onSetJobsPageSize,
  onPagePrev,
  onPageNext,
  onRefresh,
  onViewMarkdown,
}: ScrapeJobsViewProps) {
  const rangeLabel =
    scrapeJobs.length > 0 ? `${jobsOffset + 1}–${jobsOffset + scrapeJobs.length}` : '0'
  const canPrev = jobsOffset > 0 && !isLoading
  const canNext = jobsHasMore && !isLoading

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="oc-toolbar space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold tracking-tight md:text-lg">Scrape Jobs</h2>
            <p className="hidden text-xs text-[var(--oc-muted)] sm:block">
              Active jobs auto-refresh every 4s
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onRefresh} loading={isLoading}>
              <IconRefresh size={15} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <label className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--oc-muted)]">
              Rows
              <select
                value={jobsPageSize}
                onChange={(e) => onSetJobsPageSize(Number(e.target.value))}
                className="rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1 text-xs font-semibold text-[var(--oc-text)]"
              >
                {PAGE_SIZE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
          </div>
        </div>

        {/* Filter + pager row */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {JOB_FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => onSetJobsFilter(item.value)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  jobsFilter === item.value
                    ? 'bg-[var(--oc-accent)] text-white'
                    : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
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
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white text-[var(--oc-text)] transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <IconChevronLeft size={16} />
            </button>
            <span className="oc-kbd">{rangeLabel}</span>
            <button
              type="button"
              onClick={onPageNext}
              disabled={!canNext}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white text-[var(--oc-text)] transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40"
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
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--oc-border)] py-16 text-center">
          <IconGlobe size={36} className="mb-3 text-[var(--oc-border)]" />
          <p className="font-semibold text-[var(--oc-accent-ink)]">No scrape jobs</p>
          <p className="mt-1 text-sm text-[var(--oc-muted)]">
            {jobsFilter !== 'all' ? 'Try switching to "All" to see all jobs.' : 'Trigger a scrape from the Companies view.'}
          </p>
        </div>
      ) : (
        <>
          {/* Mobile cards */}
          <div className="space-y-2 md:hidden">
            {scrapeJobs.map((job) => (
              <JobCard key={job.id} job={job} onViewMarkdown={() => onViewMarkdown(job)} />
            ))}
          </div>

          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto rounded-2xl border border-[var(--oc-border)] bg-white">
            <table className="oc-compact-table min-w-[920px]">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Domain</th>
                  <th>Status</th>
                  <th>Stage 1</th>
                  <th>Stage 2</th>
                  <th>Pages</th>
                  <th>Error</th>
                  <th>Updated</th>
                  <th>View</th>
                </tr>
              </thead>
              <tbody>
                {scrapeJobs.map((job) => {
                  const badge = badgeForJob(job)
                  return (
                    <tr key={job.id}>
                      <td className="font-mono text-[11px] text-[var(--oc-muted)]" title={job.id}>
                        {job.id.slice(0, 8)}…
                      </td>
                      <td>
                        <a
                          href={job.normalized_url || `https://${job.domain}`}
                          target="_blank"
                          rel="noreferrer"
                          className="block max-w-[220px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)] hover:underline"
                          title={job.normalized_url}
                        >
                          {job.domain}
                        </a>
                      </td>
                      <td>
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                      </td>
                      <td className="text-[12px] text-[var(--oc-muted)]">{job.stage1_status}</td>
                      <td className="text-[12px] text-[var(--oc-muted)]">{job.stage2_status}</td>
                      <td className="text-[12px] tabular-nums text-[var(--oc-muted)]">
                        {job.pages_fetched_count > 0 ? (
                          <span title={`${job.pages_fetched_count} fetched, ${job.markdown_pages_count} with markdown`}>
                            <span className={job.markdown_pages_count > 0 ? 'font-semibold text-[var(--oc-text)]' : ''}>
                              {job.markdown_pages_count}
                            </span>
                            <span className="text-[var(--oc-border)]">/{job.pages_fetched_count}</span>
                          </span>
                        ) : (
                          <span className="text-[var(--oc-border)]">—</span>
                        )}
                      </td>
                      <td className="text-[12px] text-[var(--oc-muted)]">{job.last_error_code ?? '—'}</td>
                      <td className="text-[12px] text-[var(--oc-muted)]">
                        {new Date(job.updated_at).toLocaleString()}
                      </td>
                      <td>
                        {job.markdown_pages_count > 0 && (
                          <Button variant="secondary" size="xs" onClick={() => onViewMarkdown(job)}>
                            <IconEye size={13} />
                            View
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Bottom pager */}
          <div className="flex justify-end gap-1.5">
            <button
              type="button"
              onClick={onPagePrev}
              disabled={!canPrev}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <IconChevronLeft size={16} />
            </button>
            <span className="oc-kbd">{rangeLabel}</span>
            <button
              type="button"
              onClick={onPageNext}
              disabled={!canNext}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <IconChevronRight size={16} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
