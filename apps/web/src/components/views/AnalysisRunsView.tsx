import { useState } from 'react'
import type { RunRead } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { SkeletonTable } from '../ui/Skeleton'
import { IconChevronLeft, IconChevronRight, IconRefresh, IconChart, IconEye, IconUsers } from '../ui/icons'

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

interface AnalysisRunsViewProps {
  runs: RunRead[]
  isLoading: boolean
  runsOffset: number
  runsPageSize: number
  runsHasMore: boolean
  onSetRunsPageSize: (n: number) => void
  onPagePrev: () => void
  onPageNext: () => void
  onRefresh: () => void
  onInspectRun: (run: RunRead) => void
  onFetchContactsForRun: (run: RunRead) => Promise<void>
}

function runBadge(run: RunRead): { variant: 'info' | 'success' | 'fail'; label: string } {
  if (run.status === 'running' || run.status === 'created') return { variant: 'info', label: 'Running' }
  if (run.status === 'failed') return { variant: 'fail', label: 'Failed' }
  return { variant: 'success', label: 'Done' }
}

function RunProgressBar({ run }: { run: RunRead }) {
  const done = run.completed_jobs + run.failed_jobs
  const pct = run.total_jobs > 0 ? Math.round((done / run.total_jobs) * 100) : 0
  return (
    <div className="mt-1 flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--oc-border)]">
        <div
          className="h-full rounded-full bg-[var(--oc-accent)] transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[10px] tabular-nums text-[var(--oc-muted)]">{pct}%</span>
    </div>
  )
}

function RunCard({ run, onInspect, onFetchContacts, isFetching }: { run: RunRead; onInspect: () => void; onFetchContacts: () => void; isFetching: boolean }) {
  const badge = runBadge(run)
  const done = run.completed_jobs + run.failed_jobs
  return (
    <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-[var(--oc-accent-ink)]">{run.prompt_name}</p>
          <p className="mt-0.5 font-mono text-[10px] text-[var(--oc-muted)]">{run.id.slice(0, 8)}…</p>
        </div>
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>
      <RunProgressBar run={run} />
      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-[var(--oc-muted)]">
        <span>{done}/{run.total_jobs} jobs · {run.failed_jobs} failed</span>
        <div className="flex items-center gap-1.5">
          <Button variant="ghost" size="xs" onClick={onFetchContacts} loading={isFetching} title="Queue contact fetch for all Possible companies in this run">
            <IconUsers size={13} />
            Contacts
          </Button>
          <Button variant="secondary" size="xs" onClick={onInspect}>
            <IconEye size={13} />
            Inspect
          </Button>
        </div>
      </div>
      <p className="mt-1 text-[11px] text-[var(--oc-muted)]">
        {parseUTC(run.created_at).toLocaleString()}
      </p>
    </div>
  )
}

export function AnalysisRunsView({
  runs,
  isLoading,
  runsOffset,
  runsPageSize,
  runsHasMore,
  onSetRunsPageSize,
  onPagePrev,
  onPageNext,
  onRefresh,
  onInspectRun,
  onFetchContactsForRun,
}: AnalysisRunsViewProps) {
  const [fetchingRunIds, setFetchingRunIds] = useState<Set<string>>(new Set())

  const handleFetchContacts = async (run: RunRead) => {
    setFetchingRunIds((prev) => new Set(prev).add(run.id))
    try {
      await onFetchContactsForRun(run)
    } finally {
      setFetchingRunIds((prev) => { const next = new Set(prev); next.delete(run.id); return next })
    }
  }

  const rangeLabel = runs.length > 0 ? `${runsOffset + 1}–${runsOffset + runs.length}` : '0'
  const canPrev = runsOffset > 0 && !isLoading
  const canNext = runsHasMore && !isLoading

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="oc-toolbar space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold tracking-tight md:text-lg">Analysis Runs</h2>
            <p className="hidden text-xs text-[var(--oc-muted)] sm:block">
              Active runs auto-refresh every 4s
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
                value={runsPageSize}
                onChange={(e) => onSetRunsPageSize(Number(e.target.value))}
                className="rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1 text-xs font-semibold text-[var(--oc-text)]"
              >
                {PAGE_SIZE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <div className="flex items-center gap-1">
              <button type="button" onClick={onPagePrev} disabled={!canPrev}
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40">
                <IconChevronLeft size={16} />
              </button>
              <span className="oc-kbd">{rangeLabel}</span>
              <button type="button" onClick={onPageNext} disabled={!canNext}
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40">
                <IconChevronRight size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      {isLoading && runs.length === 0 ? (
        <SkeletonTable rows={4} />
      ) : runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--oc-border)] py-16 text-center">
          <IconChart size={36} className="mb-3 text-[var(--oc-border)]" />
          <p className="font-semibold text-[var(--oc-accent-ink)]">No analysis runs yet</p>
          <p className="mt-1 text-sm text-[var(--oc-muted)]">
            Select companies with completed scrapes and click Classify.
          </p>
        </div>
      ) : (
        <>
          {/* Mobile cards */}
          <div className="space-y-2 md:hidden">
            {runs.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                onInspect={() => onInspectRun(run)}
                onFetchContacts={() => void handleFetchContacts(run)}
                isFetching={fetchingRunIds.has(run.id)}
              />
            ))}
          </div>

          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto rounded-2xl border border-[var(--oc-border)] bg-white">
            <table className="oc-compact-table min-w-[820px]">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Prompt</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Failed</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const badge = runBadge(run)
                  const done = run.completed_jobs + run.failed_jobs
                  return (
                    <tr key={run.id}>
                      <td className="font-mono text-[11px] text-[var(--oc-muted)]" title={run.id}>
                        {run.id.slice(0, 8)}…
                      </td>
                      <td>
                        <span className="block max-w-[240px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)]">
                          {run.prompt_name}
                        </span>
                      </td>
                      <td>
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--oc-border)]">
                            <div
                              className="h-full rounded-full bg-[var(--oc-accent)] transition-[width] duration-500"
                              style={{ width: `${run.total_jobs > 0 ? Math.round((done / run.total_jobs) * 100) : 0}%` }}
                            />
                          </div>
                          <span className="font-mono text-[11px] tabular-nums text-[var(--oc-muted)]">
                            {done}/{run.total_jobs}
                          </span>
                        </div>
                      </td>
                      <td className="text-[12px] text-[var(--oc-muted)]">{run.failed_jobs}</td>
                      <td className="text-[12px] text-[var(--oc-muted)]">
                        {parseUTC(run.created_at).toLocaleString()}
                      </td>
                      <td>
                        <div className="flex items-center gap-1.5">
                          <Button variant="ghost" size="xs" onClick={() => void handleFetchContacts(run)} loading={fetchingRunIds.has(run.id)} title="Queue contact fetch for all Possible companies in this run">
                            <IconUsers size={13} />
                            Contacts
                          </Button>
                          <Button variant="secondary" size="xs" onClick={() => onInspectRun(run)}>
                            <IconEye size={13} />
                            Inspect
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Bottom pager */}
          <div className="flex justify-end gap-1.5">
            <button type="button" onClick={onPagePrev} disabled={!canPrev}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40">
              <IconChevronLeft size={16} />
            </button>
            <span className="oc-kbd">{rangeLabel}</span>
            <button type="button" onClick={onPageNext} disabled={!canNext}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40">
              <IconChevronRight size={16} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
