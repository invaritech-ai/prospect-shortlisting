import type { AnalyticsSnapshot, CompanyCounts, StatsResponse } from '../../lib/types'
import type { CountBucket } from '../../lib/telemetry'
import { Button } from '../ui/Button'
import { IconPulse, IconRefresh, IconChart } from '../ui/icons'

interface AnalyticsSnapshotViewProps {
  stats: StatsResponse | null
  companyCounts: CompanyCounts | null
  snapshot: AnalyticsSnapshot
  scrapeErrors: CountBucket[]
  failedRunPrompts: CountBucket[]
  isLoading: boolean
  error: string
  onRefresh: () => void
}

function fmtPct(value: number | null): string {
  return value === null ? 'N/A' : `${value.toFixed(1)}%`
}

function MetricCard({
  label,
  value,
  tone = 'default',
  hint,
}: {
  label: string
  value: string
  tone?: 'default' | 'success' | 'warn' | 'danger'
  hint?: string
}) {
  const toneClass = {
    default: 'text-[var(--oc-accent-ink)]',
    success: 'text-emerald-700',
    warn: 'text-amber-700',
    danger: 'text-rose-700',
  }[tone]
  return (
    <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">{label}</p>
      <p className={`mt-2 text-2xl font-extrabold tracking-tight ${toneClass}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-[var(--oc-muted)]">{hint}</p>}
    </div>
  )
}

function BucketList({ title, buckets }: { title: string; buckets: CountBucket[] }) {
  return (
    <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">{title}</p>
      {buckets.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--oc-muted)]">No data in current snapshot.</p>
      ) : (
        <div className="mt-3 space-y-2">
          {buckets.map((bucket) => (
            <div key={bucket.label} className="flex items-center justify-between gap-2">
              <span className="truncate text-sm text-[var(--oc-text)]">{bucket.label}</span>
              <span className="rounded-md bg-[var(--oc-surface)] px-2 py-0.5 font-mono text-xs text-[var(--oc-muted)]">
                {bucket.count}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatusSplit({
  label,
  active,
  completed,
  failed,
  total,
}: {
  label: string
  active: number
  completed: number
  failed: number
  total: number
}) {
  const safeTotal = Math.max(total, 1)
  const activePct = (active / safeTotal) * 100
  const completedPct = (completed / safeTotal) * 100
  const failedPct = (failed / safeTotal) * 100

  return (
    <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-bold text-[var(--oc-accent-ink)]">{label}</p>
        <span className="font-mono text-[11px] text-[var(--oc-muted)]">{total} sample</span>
      </div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-white">
        <div style={{ width: `${completedPct}%` }} className="bg-emerald-500" title={`Completed ${completed}`} />
        <div style={{ width: `${activePct}%` }} className="bg-[var(--oc-accent)]" title={`Active ${active}`} />
        <div style={{ width: `${failedPct}%` }} className="bg-rose-500" title={`Failed ${failed}`} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[var(--oc-muted)]">
        <span className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-700">Done {completed}</span>
        <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-700">Active {active}</span>
        <span className="rounded bg-rose-50 px-2 py-0.5 text-rose-700">Failed {failed}</span>
      </div>
    </div>
  )
}

export function AnalyticsSnapshotView({
  stats,
  companyCounts,
  snapshot,
  scrapeErrors,
  failedRunPrompts,
  isLoading,
  error,
  onRefresh,
}: AnalyticsSnapshotViewProps) {
  const scrapePctDone = stats ? `${stats.scrape.pct_done.toFixed(1)}%` : 'N/A'
  const analysisPctDone = stats ? `${stats.analysis.pct_done.toFixed(1)}%` : 'N/A'
  const asOf = stats ? new Date(stats.as_of).toLocaleString() : null

  return (
    <div className="space-y-3">
      <div className="oc-toolbar space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold tracking-tight md:text-lg">Analytics Snapshot</h2>
            <p className="text-xs text-[var(--oc-muted)]">
              Live Snapshot · no historical persistence
              {asOf ? ` · as of ${asOf}` : ''}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={onRefresh} loading={isLoading}>
            <IconRefresh size={15} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-3">
          <p className="text-sm text-rose-800">{error}</p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Companies (Total)" value={companyCounts ? companyCounts.total.toLocaleString() : 'N/A'} />
        <MetricCard label="Possible Ratio" value={fmtPct(snapshot.possible_ratio_pct)} tone="success" />
        <MetricCard label="Scrape Progress" value={scrapePctDone} hint={stats ? `${stats.scrape.completed}/${stats.scrape.total}` : undefined} />
        <MetricCard label="Analysis Progress" value={analysisPctDone} hint={stats ? `${stats.analysis.completed}/${stats.analysis.total}` : undefined} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <IconPulse size={16} className="text-[var(--oc-accent)]" />
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Pipeline Pressure</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <MetricCard
              label="Scrape Queue"
              value={stats ? `${stats.scrape.queued + stats.scrape.running}` : 'N/A'}
              tone={stats && stats.scrape.stuck_count > 0 ? 'warn' : 'default'}
              hint={stats ? `${stats.scrape.stuck_count} stuck` : undefined}
            />
            <MetricCard
              label="Analysis Queue"
              value={stats ? `${stats.analysis.queued + stats.analysis.running}` : 'N/A'}
              tone={stats && stats.analysis.stuck_count > 0 ? 'warn' : 'default'}
              hint={stats ? `${stats.analysis.stuck_count} stuck` : undefined}
            />
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <IconChart size={16} className="text-[var(--oc-accent)]" />
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Recent Sample Quality</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <MetricCard
              label="Scrape Failure Rate"
              value={fmtPct(snapshot.scrape_failure_pct)}
              tone={(snapshot.scrape_failure_pct ?? 0) > 25 ? 'danger' : 'default'}
              hint={`${snapshot.scrape_sample_failed}/${snapshot.scrape_sample_total}`}
            />
            <MetricCard
              label="Analysis Failure Rate"
              value={fmtPct(snapshot.analysis_failure_pct)}
              tone={(snapshot.analysis_failure_pct ?? 0) > 25 ? 'danger' : 'default'}
              hint={`${snapshot.run_sample_failed}/${snapshot.run_sample_total}`}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <StatusSplit
          label="Scrape Sample State Split"
          active={snapshot.scrape_sample_active}
          completed={snapshot.scrape_sample_completed}
          failed={snapshot.scrape_sample_failed}
          total={snapshot.scrape_sample_total}
        />
        <StatusSplit
          label="Analysis Sample State Split"
          active={snapshot.run_sample_active}
          completed={snapshot.run_sample_completed}
          failed={snapshot.run_sample_failed}
          total={snapshot.run_sample_total}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <BucketList title="Top Scrape Error Codes (sample)" buckets={scrapeErrors} />
        <BucketList title="Failed Runs by Prompt (sample)" buckets={failedRunPrompts} />
      </div>
    </div>
  )
}
