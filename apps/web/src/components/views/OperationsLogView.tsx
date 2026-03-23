import type { OperationsEvent, OperationsEventKind, OperationsEventStatus } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { SkeletonTable } from '../ui/Skeleton'
import { IconRefresh, IconTimeline, IconEye } from '../ui/icons'

type PipelineFilter = 'all' | OperationsEventKind
type StatusFilter = 'all' | OperationsEventStatus

interface OperationsLogViewProps {
  events: OperationsEvent[]
  isLoading: boolean
  error: string
  pipelineFilter: PipelineFilter
  statusFilter: StatusFilter
  errorOnly: boolean
  searchQuery: string
  activeCount: number
  onSetPipelineFilter: (value: PipelineFilter) => void
  onSetStatusFilter: (value: StatusFilter) => void
  onSetErrorOnly: (value: boolean) => void
  onSetSearchQuery: (value: string) => void
  onRefresh: () => void
  onInspectEvent: (event: OperationsEvent) => void
}

function statusBadge(status: OperationsEventStatus): { variant: 'info' | 'success' | 'fail'; label: string } {
  if (status === 'active') return { variant: 'info', label: 'Active' }
  if (status === 'completed') return { variant: 'success', label: 'Completed' }
  return { variant: 'fail', label: 'Failed' }
}

function kindBadge(kind: OperationsEventKind): { variant: 'info' | 'neutral'; label: string } {
  if (kind === 'scrape') return { variant: 'info', label: 'Scrape' }
  return { variant: 'neutral', label: 'Analysis' }
}

const PIPELINE_FILTERS: Array<{ value: PipelineFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'scrape', label: 'Scrape' },
  { value: 'analysis', label: 'Analysis' },
]

const STATUS_FILTERS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All states' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

export function OperationsLogView({
  events,
  isLoading,
  error,
  pipelineFilter,
  statusFilter,
  errorOnly,
  searchQuery,
  activeCount,
  onSetPipelineFilter,
  onSetStatusFilter,
  onSetErrorOnly,
  onSetSearchQuery,
  onRefresh,
  onInspectEvent,
}: OperationsLogViewProps) {
  return (
    <div className="space-y-3">
      <div className="oc-toolbar space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold tracking-tight md:text-lg">Operations Log</h2>
            <p className="text-xs text-[var(--oc-muted)]">
              Unified scrape and analysis timeline · live from existing endpoints
            </p>
          </div>
          <div className="flex items-center gap-2">
            {activeCount > 0 && (
              <span className="rounded-full bg-[var(--oc-accent-soft)] px-2.5 py-1 text-[11px] font-bold text-[var(--oc-accent-ink)]">
                {activeCount} active
              </span>
            )}
            <Button variant="secondary" size="sm" onClick={onRefresh} loading={isLoading}>
              <IconRefresh size={15} />
              Refresh
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {PIPELINE_FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => onSetPipelineFilter(item.value)}
                className={`min-h-9 rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  pipelineFilter === item.value
                    ? 'bg-[var(--oc-accent)] text-white'
                    : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="h-4 w-px bg-[var(--oc-border)] mx-1" />

          <div className="flex flex-wrap items-center gap-1.5">
            {STATUS_FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => onSetStatusFilter(item.value)}
                className={`min-h-9 rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  statusFilter === item.value
                    ? 'bg-slate-700 text-white'
                    : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <label className="ml-auto flex min-h-9 items-center gap-2 rounded-lg border border-[var(--oc-border)] bg-white px-2.5 py-1.5 text-xs font-semibold text-[var(--oc-muted)]">
            <input
              type="checkbox"
              checked={errorOnly}
              onChange={(e) => onSetErrorOnly(e.target.checked)}
              className="rounded border-[var(--oc-border)]"
            />
            Error only
          </label>
        </div>

        <input
          type="search"
          value={searchQuery}
          onChange={(e) => onSetSearchQuery(e.target.value)}
          placeholder="Search domain, prompt, id, or error code"
          className="w-full rounded-xl border border-[var(--oc-border)] bg-white px-3 py-2.5 text-sm text-[var(--oc-text)] placeholder:text-[var(--oc-muted)]"
        />
      </div>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-3">
          <p className="text-sm text-rose-800">{error}</p>
        </div>
      )}

      {isLoading && events.length === 0 ? (
        <SkeletonTable rows={7} />
      ) : events.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--oc-border)] py-16 text-center">
          <IconTimeline size={36} className="mb-3 text-[var(--oc-border)]" />
          <p className="font-semibold text-[var(--oc-accent-ink)]">No matching events</p>
          <p className="mt-1 text-sm text-[var(--oc-muted)]">Try relaxing filters or refresh the log snapshot.</p>
        </div>
      ) : (
        <>
          <div className="space-y-2 md:hidden">
            {events.map((event) => {
              const sBadge = statusBadge(event.status)
              const kBadge = kindBadge(event.kind)
              return (
                <div key={event.id} className="rounded-2xl border border-[var(--oc-border)] bg-white p-3.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-[var(--oc-accent-ink)]">{event.title}</p>
                      <p className="mt-0.5 truncate font-mono text-[10px] text-[var(--oc-muted)]">{event.subtitle}</p>
                    </div>
                    <div className="flex flex-col gap-1">
                      <Badge variant={kBadge.variant}>{kBadge.label}</Badge>
                      <Badge variant={sBadge.variant}>{sBadge.label}</Badge>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <p className="text-[11px] text-[var(--oc-muted)]">{parseUTC(event.occurred_at).toLocaleString()}</p>
                    <Button variant="secondary" size="xs" onClick={() => onInspectEvent(event)}>
                      <IconEye size={13} />
                      Inspect
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="hidden md:block overflow-x-auto rounded-2xl border border-[var(--oc-border)] bg-white">
            <table className="oc-compact-table min-w-[980px]">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Pipeline</th>
                  <th>Status</th>
                  <th>Title</th>
                  <th>Details</th>
                  <th>Error</th>
                  <th>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => {
                  const sBadge = statusBadge(event.status)
                  const kBadge = kindBadge(event.kind)
                  return (
                    <tr key={event.id}>
                      <td className="text-[12px] text-[var(--oc-muted)]">
                        {parseUTC(event.occurred_at).toLocaleString()}
                      </td>
                      <td><Badge variant={kBadge.variant}>{kBadge.label}</Badge></td>
                      <td><Badge variant={sBadge.variant}>{sBadge.label}</Badge></td>
                      <td className="font-semibold text-[var(--oc-accent-ink)]">{event.title}</td>
                      <td className="font-mono text-[11px] text-[var(--oc-muted)]">{event.subtitle}</td>
                      <td className="text-[12px] text-[var(--oc-muted)]">{event.error_code ?? '—'}</td>
                      <td>
                        <Button variant="secondary" size="xs" onClick={() => onInspectEvent(event)}>
                          <IconEye size={13} />
                          Inspect
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
