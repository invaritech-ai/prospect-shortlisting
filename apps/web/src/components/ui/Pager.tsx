import { PAGE_SIZE_OPTIONS } from '../../hooks/usePipelineViews'

interface PagerProps {
  offset: number
  pageSize: number
  total: number | null
  hasMore: boolean
  onPrev: () => void
  onNext: () => void
  onPageSizeChange: (size: number) => void
}

export function Pager({ offset, pageSize, total, hasMore, onPrev, onNext, onPageSizeChange }: PagerProps) {
  const from = offset + 1
  const to = offset + pageSize // actual row count comes from the table, so this is the max
  const canPrev = offset > 0
  const canNext = hasMore

  const rangeLabel = total != null
    ? `${from.toLocaleString()}–${Math.min(to, total).toLocaleString()} of ${total.toLocaleString()}`
    : `${from.toLocaleString()}–${to.toLocaleString()}`

  return (
    <div className="flex items-center gap-2">
      <label className="flex items-center gap-1 text-[11px] font-semibold text-(--oc-muted)">
        Rows
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="ml-1 rounded-md border border-(--oc-border) bg-(--oc-surface-strong) px-1.5 py-0.5 text-xs font-semibold text-(--oc-text)"
        >
          {PAGE_SIZE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <button
        type="button"
        onClick={onPrev}
        disabled={!canPrev}
        className="flex h-6 w-6 items-center justify-center rounded-md border border-(--oc-border) bg-(--oc-surface-strong) text-(--oc-text) text-xs transition hover:bg-(--oc-surface) disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="Previous page"
      >
        ‹
      </button>
      <span className="min-w-[90px] text-center text-[11px] font-medium text-(--oc-muted)">{rangeLabel}</span>
      <button
        type="button"
        onClick={onNext}
        disabled={!canNext}
        className="flex h-6 w-6 items-center justify-center rounded-md border border-(--oc-border) bg-(--oc-surface-strong) text-(--oc-text) text-xs transition hover:bg-(--oc-surface) disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="Next page"
      >
        ›
      </button>
    </div>
  )
}
