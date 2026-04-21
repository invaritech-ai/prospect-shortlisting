import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type {
  CostLineItem,
  CostStatsResponse,
  OperationsEvent,
  OperationsEventKind,
  OperationsEventStatus,
  PipelineCostSummaryRead,
} from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { SkeletonTable } from '../ui/Skeleton'
import { IconRefresh, IconTimeline, IconEye } from '../ui/icons'

type PipelineFilter = 'all' | OperationsEventKind
type StatusFilter = 'all' | OperationsEventStatus

const VIRTUAL_ROW_THRESHOLD = 50
const EVENT_TABLE_ROW_ESTIMATE_PX = 52
const MOBILE_EVENT_CARD_ESTIMATE_PX = 120
const COST_TABLE_ROW_ESTIMATE_PX = 48

function useMediaMinMd(): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 768px)').matches
      : true
  )
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(min-width: 768px)')
    setMatches(mq.matches)
    const onChange = () => setMatches(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return matches
}

interface OperationsLogViewProps {
  activeCampaignName: string | null
  campaignCostSummary: PipelineCostSummaryRead | null
  campaignCostBreakdown: CostStatsResponse | null
  events: OperationsEvent[]
  isLoading: boolean
  error: string
  pipelineFilter: PipelineFilter
  statusFilter: StatusFilter
  errorOnly: boolean
  searchQuery: string
  activeCount: number
  showScrapeFilter: boolean
  scrapeTelemetryNote?: string
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

const STATUS_FILTERS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All states' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

const CHIP_SELECTED = 'bg-[var(--oc-accent)] text-white'
const CHIP_IDLE =
  'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'

function CostDomainMobileCard({
  row,
  formatUsd,
}: {
  row: CostLineItem
  formatUsd: (value: number | string | null | undefined) => string
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-3.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start justify-between gap-2 text-left"
        aria-expanded={open}
        aria-label={open ? `Collapse cost stages for ${row.domain}` : `Expand cost stages for ${row.domain}`}
      >
        <div className="min-w-0">
          <p className="font-semibold text-[var(--oc-accent-ink)]">{row.domain}</p>
          <p className="mt-0.5 text-xs text-[var(--oc-muted)]">
            Total {formatUsd(row.overall)}
            <span className="ml-1 text-[11px]" aria-hidden="true">
              {open ? '▴' : '▾'}
            </span>
          </p>
        </div>
      </button>
      {open ? (
        <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-[var(--oc-border)] pt-3 text-xs">
          <dt className="text-[var(--oc-muted)]">S1 Scrape</dt>
          <dd className="text-right font-mono tabular-nums text-[var(--oc-text)]">{formatUsd(row.scrape)}</dd>
          <dt className="text-[var(--oc-muted)]">S2 Analysis</dt>
          <dd className="text-right font-mono tabular-nums text-[var(--oc-text)]">{formatUsd(row.analysis)}</dd>
          <dt className="text-[var(--oc-muted)]">S3 Contact fetch</dt>
          <dd className="text-right font-mono tabular-nums text-[var(--oc-text)]">{formatUsd(row.contact_fetch)}</dd>
          <dt className="text-[var(--oc-muted)]">S4 Validation</dt>
          <dd className="text-right font-mono tabular-nums text-[var(--oc-text)]">{formatUsd(row.validation)}</dd>
        </dl>
      ) : null}
    </div>
  )
}

function costTableHead() {
  return (
    <thead className="sticky top-0 z-[2] bg-[var(--oc-surface)] shadow-[inset_0_-1px_0_var(--oc-border)]">
      <tr>
        <th scope="col" className="bg-[var(--oc-surface)]">
          Domain
        </th>
        <th scope="col" className="bg-[var(--oc-surface)] text-right tabular-nums">
          <abbr title="Scrape" className="cursor-help no-underline">
            S1
          </abbr>
        </th>
        <th scope="col" className="bg-[var(--oc-surface)] text-right tabular-nums">
          <abbr title="Analysis" className="cursor-help no-underline">
            S2
          </abbr>
        </th>
        <th scope="col" className="bg-[var(--oc-surface)] text-right tabular-nums">
          <abbr title="Contact fetch" className="cursor-help no-underline">
            S3
          </abbr>
        </th>
        <th scope="col" className="bg-[var(--oc-surface)] text-right tabular-nums">
          <abbr title="Validation" className="cursor-help no-underline">
            S4
          </abbr>
        </th>
        <th scope="col" className="bg-[var(--oc-surface)] text-right tabular-nums">
          Total
        </th>
      </tr>
    </thead>
  )
}

function DesktopCostTableBodySimple({
  items,
  formatUsd,
}: {
  items: CostLineItem[]
  formatUsd: (value: number | string | null | undefined) => string
}) {
  return (
    <>
      {items.map((row) => (
        <tr key={row.company_id}>
          <td className="font-semibold text-[var(--oc-accent-ink)]">{row.domain}</td>
          <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.scrape)}</td>
          <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.analysis)}</td>
          <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.contact_fetch)}</td>
          <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.validation)}</td>
          <td className="text-right tabular-nums font-semibold text-[var(--oc-accent-ink)]">
            {formatUsd(row.overall)}
          </td>
        </tr>
      ))}
    </>
  )
}

function DesktopCostTableBodyVirtual({
  items,
  formatUsd,
  campaignLabel,
}: {
  items: CostLineItem[]
  formatUsd: (value: number | string | null | undefined) => string
  campaignLabel: string
}) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => COST_TABLE_ROW_ESTIMATE_PX,
    overscan: 8,
  })
  const virtualRows = virtualizer.getVirtualItems()
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0
  const paddingBottom =
    virtualRows.length > 0 ? virtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end : 0

  return (
    <div
      ref={parentRef}
      className="max-h-[40vh] overflow-y-auto overflow-x-auto rounded-xl border border-[var(--oc-border)]"
    >
      <table className="oc-compact-table min-w-[760px]">
        <caption className="sr-only">
          Per-domain LLM campaign cost breakdown by pipeline stage for {campaignLabel}
        </caption>
        {costTableHead()}
        <tbody>
          {paddingTop > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={6} style={{ height: `${paddingTop}px` }} className="!p-0 !border-0" />
            </tr>
          ) : null}
          {virtualRows.map((vr) => {
            const row = items[vr.index]
            return (
              <tr key={row.company_id}>
                <td className="font-semibold text-[var(--oc-accent-ink)]">{row.domain}</td>
                <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.scrape)}</td>
                <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.analysis)}</td>
                <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.contact_fetch)}</td>
                <td className="text-right tabular-nums text-[var(--oc-muted)]">{formatUsd(row.validation)}</td>
                <td className="text-right tabular-nums font-semibold text-[var(--oc-accent-ink)]">
                  {formatUsd(row.overall)}
                </td>
              </tr>
            )
          })}
          {paddingBottom > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={6} style={{ height: `${paddingBottom}px` }} className="!p-0 !border-0" />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

function DesktopCostTable({
  items,
  formatUsd,
  campaignLabel,
}: {
  items: CostLineItem[]
  formatUsd: (value: number | string | null | undefined) => string
  campaignLabel: string
}) {
  if (items.length >= VIRTUAL_ROW_THRESHOLD) {
    return <DesktopCostTableBodyVirtual items={items} formatUsd={formatUsd} campaignLabel={campaignLabel} />
  }
  return (
    <div className="max-h-[40vh] overflow-y-auto overflow-x-auto rounded-xl border border-[var(--oc-border)]">
      <table className="oc-compact-table min-w-[760px]">
        <caption className="sr-only">
          Per-domain LLM campaign cost breakdown by pipeline stage for {campaignLabel}
        </caption>
        {costTableHead()}
        <tbody>
          <DesktopCostTableBodySimple items={items} formatUsd={formatUsd} />
        </tbody>
      </table>
    </div>
  )
}

function DesktopEventsTableBodySimple({
  events,
  onInspectEvent,
}: {
  events: OperationsEvent[]
  onInspectEvent: (event: OperationsEvent) => void
}) {
  return (
    <>
      {events.map((event) => (
        <DesktopEventRow key={event.id} event={event} onInspectEvent={onInspectEvent} />
      ))}
    </>
  )
}

function DesktopEventRow({
  event,
  onInspectEvent,
}: {
  event: OperationsEvent
  onInspectEvent: (event: OperationsEvent) => void
}) {
  const sBadge = statusBadge(event.status)
  const kBadge = kindBadge(event.kind)
  return (
    <tr>
      <td className="text-[12px] text-[var(--oc-muted)]">{parseUTC(event.occurred_at).toLocaleString()}</td>
      <td>
        <Badge variant={kBadge.variant}>{kBadge.label}</Badge>
      </td>
      <td>
        <Badge variant={sBadge.variant}>{sBadge.label}</Badge>
      </td>
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
}

function DesktopEventsTableBodyVirtual({
  events,
  onInspectEvent,
}: {
  events: OperationsEvent[]
  onInspectEvent: (event: OperationsEvent) => void
}) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => EVENT_TABLE_ROW_ESTIMATE_PX,
    overscan: 10,
  })
  const virtualRows = virtualizer.getVirtualItems()
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0
  const paddingBottom =
    virtualRows.length > 0 ? virtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end : 0

  return (
    <div
      ref={parentRef}
      className="max-h-[min(60vh,800px)] overflow-auto rounded-2xl border border-[var(--oc-border)] bg-white"
    >
      <table className="oc-compact-table min-w-[980px]">
        <caption className="sr-only">Campaign operations event log</caption>
        <thead className="sticky top-0 z-[2] bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)] shadow-[inset_0_-1px_0_var(--oc-border)] backdrop-blur-sm">
          <tr>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Time</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Pipeline</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Status</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Title</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Details</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Error</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Inspect</th>
          </tr>
        </thead>
        <tbody>
          {paddingTop > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={7} style={{ height: `${paddingTop}px` }} className="!p-0 !border-0" />
            </tr>
          ) : null}
          {virtualRows.map((vr) => (
            <DesktopEventRow key={events[vr.index].id} event={events[vr.index]} onInspectEvent={onInspectEvent} />
          ))}
          {paddingBottom > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={7} style={{ height: `${paddingBottom}px` }} className="!p-0 !border-0" />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  )
}

function DesktopEventsTable({
  events,
  onInspectEvent,
}: {
  events: OperationsEvent[]
  onInspectEvent: (event: OperationsEvent) => void
}) {
  if (events.length >= VIRTUAL_ROW_THRESHOLD) {
    return <DesktopEventsTableBodyVirtual events={events} onInspectEvent={onInspectEvent} />
  }
  return (
    <div className="max-h-[min(60vh,800px)] overflow-auto rounded-2xl border border-[var(--oc-border)] bg-white">
      <table className="oc-compact-table min-w-[980px]">
        <caption className="sr-only">Campaign operations event log</caption>
        <thead className="sticky top-0 z-[2] bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)] shadow-[inset_0_-1px_0_var(--oc-border)] backdrop-blur-sm">
          <tr>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Time</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Pipeline</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Status</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Title</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Details</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Error</th>
            <th scope="col" className="bg-[color-mix(in_srgb,var(--oc-surface-strong)_96%,white)]">Inspect</th>
          </tr>
        </thead>
        <tbody>
          <DesktopEventsTableBodySimple events={events} onInspectEvent={onInspectEvent} />
        </tbody>
      </table>
    </div>
  )
}

function MobileEventCard({
  event,
  onInspectEvent,
}: {
  event: OperationsEvent
  onInspectEvent: (event: OperationsEvent) => void
}) {
  const sBadge = statusBadge(event.status)
  const kBadge = kindBadge(event.kind)
  return (
    <div className="rounded-2xl border border-[var(--oc-border)] bg-white p-3.5">
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
}

function MobileEventsCardsSimple({
  events,
  onInspectEvent,
}: {
  events: OperationsEvent[]
  onInspectEvent: (event: OperationsEvent) => void
}) {
  return (
    <div className="space-y-2">
      {events.map((event) => (
        <MobileEventCard key={event.id} event={event} onInspectEvent={onInspectEvent} />
      ))}
    </div>
  )
}

function MobileEventsCardsVirtual({
  events,
  onInspectEvent,
}: {
  events: OperationsEvent[]
  onInspectEvent: (event: OperationsEvent) => void
}) {
  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => MOBILE_EVENT_CARD_ESTIMATE_PX,
    overscan: 6,
  })

  return (
    <div ref={parentRef} className="max-h-[min(70vh,900px)] overflow-auto pr-1">
      <div
        className="relative w-full"
        style={{ height: `${virtualizer.getTotalSize()}px` }}
      >
        {virtualizer.getVirtualItems().map((vr) => (
          <div
            key={vr.key}
            data-index={vr.index}
            ref={virtualizer.measureElement}
            className="absolute left-0 top-0 w-full pb-2"
            style={{ transform: `translateY(${vr.start}px)` }}
          >
            <MobileEventCard event={events[vr.index]} onInspectEvent={onInspectEvent} />
          </div>
        ))}
      </div>
    </div>
  )
}

function MobileEventsCards({
  events,
  onInspectEvent,
}: {
  events: OperationsEvent[]
  onInspectEvent: (event: OperationsEvent) => void
}) {
  if (events.length >= VIRTUAL_ROW_THRESHOLD) {
    return <MobileEventsCardsVirtual events={events} onInspectEvent={onInspectEvent} />
  }
  return <MobileEventsCardsSimple events={events} onInspectEvent={onInspectEvent} />
}

export function OperationsLogView({
  activeCampaignName,
  campaignCostSummary,
  campaignCostBreakdown,
  events,
  isLoading,
  error,
  pipelineFilter,
  statusFilter,
  errorOnly,
  searchQuery,
  activeCount,
  showScrapeFilter,
  scrapeTelemetryNote,
  onSetPipelineFilter,
  onSetStatusFilter,
  onSetErrorOnly,
  onSetSearchQuery,
  onRefresh,
  onInspectEvent,
}: OperationsLogViewProps) {
  const isDesktop = useMediaMinMd()
  const formatUsd = (value: number | string | null | undefined) => `$${Number(value ?? 0).toFixed(4)}`

  const sortedCostItems = useMemo(() => {
    if (!campaignCostBreakdown?.items.length) return []
    return [...campaignCostBreakdown.items].sort(
      (a, b) => Number(b.overall ?? 0) - Number(a.overall ?? 0)
    )
  }, [campaignCostBreakdown])

  const pipelineFilters: Array<{ value: PipelineFilter; label: string }> = [
    { value: 'all', label: 'All' },
    ...(showScrapeFilter ? [{ value: 'scrape' as const, label: 'Scrape' }] : []),
    { value: 'analysis', label: 'Analysis' },
  ]

  const costCampaignLabel = activeCampaignName ?? 'Selected campaign'

  return (
    <div className="space-y-3">
      <div className="oc-toolbar space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold tracking-tight md:text-lg">Operations Log</h2>
            <p className="text-xs text-[var(--oc-muted)]">
              Campaign-scoped analysis timeline and cost observability.
            </p>
            {scrapeTelemetryNote ? (
              <p className="mt-1 text-[11px] text-[var(--oc-muted)]">{scrapeTelemetryNote}</p>
            ) : null}
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
            {pipelineFilters.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => onSetPipelineFilter(item.value)}
                className={`min-h-9 rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  pipelineFilter === item.value ? CHIP_SELECTED : CHIP_IDLE
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="mx-1 h-4 w-px bg-[var(--oc-border)]" />

          <div className="flex flex-wrap items-center gap-1.5">
            {STATUS_FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => onSetStatusFilter(item.value)}
                className={`min-h-9 rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  statusFilter === item.value ? CHIP_SELECTED : CHIP_IDLE
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

        <div>
          <label htmlFor="ops-log-search" className="sr-only">
            Search operations log
          </label>
          <input
            id="ops-log-search"
            type="search"
            value={searchQuery}
            onChange={(e) => onSetSearchQuery(e.target.value)}
            placeholder="Search domain, prompt, id, or error code"
            autoComplete="off"
            className="w-full rounded-xl border border-[var(--oc-border)] bg-white px-3 py-2.5 text-sm text-[var(--oc-text)] placeholder:text-[var(--oc-muted)]"
          />
        </div>
      </div>

      {(campaignCostSummary || campaignCostBreakdown) && (
        <section className="space-y-2 rounded-2xl border border-[var(--oc-border)] bg-white p-3" aria-labelledby="ops-cost-heading">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 id="ops-cost-heading" className="text-xs font-bold uppercase tracking-wide text-[var(--oc-muted)]">
                Campaign cost observability
              </h3>
              <p className="text-sm font-semibold text-[var(--oc-accent-ink)]">{costCampaignLabel}</p>
            </div>
            {campaignCostSummary && (
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="rounded-full border border-[var(--oc-border)] bg-[var(--oc-surface)] px-3 py-1 text-[var(--oc-muted)]">
                  Total spend: {formatUsd(campaignCostSummary.total_cost_usd)}
                </span>
                <span className="rounded-full border border-[var(--oc-border)] bg-[var(--oc-surface)] px-3 py-1 text-[var(--oc-muted)]">
                  LLM events: {campaignCostSummary.event_count.toLocaleString()}
                </span>
                <span
                  className="rounded-full border border-[var(--oc-border)] bg-[var(--oc-surface)] px-3 py-1 text-[var(--oc-muted)]"
                  title="Sum of input and output tokens recorded for this campaign in the current window."
                >
                  Tokens: {(campaignCostSummary.input_tokens + campaignCostSummary.output_tokens).toLocaleString()}
                </span>
              </div>
            )}
          </div>
          <p className="text-xs text-[var(--oc-muted)]">
            <span className="font-medium text-[var(--oc-text)]">Stages: </span>
            <span className="hidden md:inline">S1 Scrape · S2 Analysis · S3 Contact fetch · S4 Validation</span>
            <span className="md:hidden">Tap a domain to expand stage costs.</span>
          </p>
          {sortedCostItems.length > 0 ? (
            <>
              <div className="space-y-2 md:hidden">
                {sortedCostItems.map((row) => (
                  <CostDomainMobileCard key={row.company_id} row={row} formatUsd={formatUsd} />
                ))}
              </div>
              <div className="hidden md:block">
                <DesktopCostTable items={sortedCostItems} formatUsd={formatUsd} campaignLabel={costCampaignLabel} />
              </div>
            </>
          ) : (
            <p className="rounded-xl border border-dashed border-[var(--oc-border)] bg-[var(--oc-surface)] px-3 py-2 text-xs text-[var(--oc-muted)]">
              No domain-level LLM cost rows yet for this campaign.
            </p>
          )}
        </section>
      )}

      {error && (
        <div className="flex flex-col gap-2 rounded-2xl border border-rose-200 bg-rose-50 p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-rose-800">{error}</p>
          <Button variant="secondary" size="sm" onClick={onRefresh} loading={isLoading}>
            Retry
          </Button>
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
        <section aria-labelledby="ops-events-heading">
          <h3 id="ops-events-heading" className="sr-only">
            Event log
          </h3>
          {isDesktop ? (
            <DesktopEventsTable events={events} onInspectEvent={onInspectEvent} />
          ) : (
            <MobileEventsCards events={events} onInspectEvent={onInspectEvent} />
          )}
        </section>
      )}
    </div>
  )
}
