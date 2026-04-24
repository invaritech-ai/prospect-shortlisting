import { useCallback, useEffect, useRef, useState } from 'react'
import type { QueueHistoryItem } from '../../lib/types'
import { getQueueHistory, parseUTC } from '../../lib/api'
import { Badge } from '../ui/Badge'
import type { BadgeVariant } from '../ui/Badge'
import { Button } from '../ui/Button'
import { IconRefresh, IconTimeline } from '../ui/icons'

interface QueueHistoryViewProps {
  campaignId: string | null
}

type ViewMode = 'live' | 'history'
type StageFilter = 'all' | 's1' | 's2' | 's3' | 's4' | 's5'

const STAGE_LABELS: Record<string, string> = {
  s1: 'S1 · Scrape',
  s2: 'S2 · AI',
  s3: 'S3 · Contacts',
  s4: 'S4 · Reveal',
  s5: 'S5 · Verify',
}

const STAGE_COLORS: Record<string, string> = {
  s1: 'var(--s1)',
  s2: 'var(--s2)',
  s3: 'var(--s3)',
  s4: 'var(--s4)',
  s5: 'var(--s5)',
}

function stateVariant(state: string): BadgeVariant {
  if (state === 'succeeded') return 'success'
  if (state === 'failed' || state === 'dead') return 'fail'
  if (state === 'running') return 'info'
  return 'neutral'
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return '—'
  const start = parseUTC(startedAt).getTime()
  const end = finishedAt ? parseUTC(finishedAt).getTime() : Date.now()
  const sec = Math.floor((end - start) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  return rem > 0 ? `${min}m ${rem}s` : `${min}m`
}

function formatTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  const d = parseUTC(dateStr)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function QueueHistoryView({ campaignId }: QueueHistoryViewProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('live')
  const [stageFilter, setStageFilter] = useState<StageFilter>('all')
  const [items, setItems] = useState<QueueHistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    if (!campaignId) return
    setIsLoading(true)
    setError('')
    try {
      const res = await getQueueHistory({
        campaignId,
        stage: stageFilter,
        view: viewMode,
        limit: 200,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load queue history')
    } finally {
      setIsLoading(false)
    }
  }, [campaignId, stageFilter, viewMode])

  useEffect(() => {
    void load()
  }, [load])

  // Auto-refresh every 20s on Live tab, paused when browser tab is hidden
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (viewMode !== 'live') return
    const tick = () => { if (!document.hidden) void load() }
    intervalRef.current = setInterval(tick, 20_000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [viewMode, load])

  const STAGE_FILTERS: StageFilter[] = ['all', 's1', 's2', 's3', 's4', 's5']

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <IconTimeline size={20} className="text-(--oc-accent-ink)" />
          <h1 className="text-lg font-bold text-(--oc-text)">Queue History</h1>
          {total > 0 && (
            <span className="rounded-full bg-(--oc-surface-strong) px-2 py-0.5 text-xs font-semibold text-(--oc-muted)">
              {total}
            </span>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={() => void load()} loading={isLoading}>
          <IconRefresh size={14} />
          Refresh
        </Button>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 rounded-xl bg-(--oc-surface-strong) p-1 self-start">
        {(['live', 'history'] as ViewMode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setViewMode(m)}
            className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
              viewMode === m
                ? 'bg-(--oc-surface) text-(--oc-accent-ink) shadow-sm'
                : 'text-(--oc-muted) hover:text-(--oc-text)'
            }`}
          >
            {m === 'live' ? 'Live' : 'History'}
            {m === 'live' && viewMode === 'live' && (
              <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
            )}
          </button>
        ))}
      </div>

      {/* Stage filter chips */}
      <div className="flex flex-wrap gap-1.5">
        {STAGE_FILTERS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStageFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition border ${
              stageFilter === s
                ? 'border-transparent text-white'
                : 'border-(--oc-border) bg-(--oc-surface) text-(--oc-muted) hover:text-(--oc-text)'
            }`}
            style={
              stageFilter === s
                ? { backgroundColor: s === 'all' ? 'var(--oc-accent)' : STAGE_COLORS[s] }
                : {}
            }
          >
            {s === 'all' ? 'All stages' : STAGE_LABELS[s]}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          {error}
        </p>
      )}

      {/* No campaign selected */}
      {!campaignId && (
        <div className="flex flex-1 items-center justify-center text-(--oc-muted) text-sm">
          Select a campaign to view queue history.
        </div>
      )}

      {/* Empty state */}
      {campaignId && !isLoading && items.length === 0 && !error && (
        <div className="flex flex-1 items-center justify-center text-(--oc-muted) text-sm">
          {viewMode === 'live' ? 'No active jobs right now.' : 'No completed jobs yet.'}
        </div>
      )}

      {/* Table */}
      {items.length > 0 && (
        <div className="flex-1 overflow-auto rounded-xl border border-(--oc-border)">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-(--oc-surface-strong) text-left text-xs font-semibold uppercase tracking-wide text-(--oc-muted)">
              <tr>
                <th className="px-4 py-3">Stage</th>
                <th className="px-4 py-3">Domain</th>
                <th className="px-4 py-3">State</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Started</th>
                <th className="px-4 py-3">Duration</th>
                <th className="px-4 py-3">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-(--oc-border) bg-(--oc-surface)">
              {items.map((item) => (
                <tr key={item.id} className="hover:bg-(--oc-surface-strong) transition-colors">
                  <td className="px-4 py-3">
                    <span
                      className="inline-block rounded-md px-2 py-0.5 text-[11px] font-bold text-white"
                      style={{ backgroundColor: STAGE_COLORS[item.stage] }}
                    >
                      {item.stage.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-(--oc-text)">
                    {item.company_domain ?? <span className="text-(--oc-muted)">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={stateVariant(item.state)}>{item.state}</Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums text-(--oc-muted) text-xs">
                    {formatTime(item.created_at)}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-(--oc-muted) text-xs">
                    {formatTime(item.started_at)}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-xs text-(--oc-text)">
                    {formatDuration(item.started_at, item.finished_at)}
                    {item.state === 'running' && (
                      <span className="ml-1 text-(--oc-muted)">…</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {item.error_code ? (
                      <span className="font-mono text-[11px] text-red-500">{item.error_code}</span>
                    ) : (
                      <span className="text-(--oc-muted)">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
