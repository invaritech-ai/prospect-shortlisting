import { PAGE_SIZE_OPTIONS } from '../../hooks/usePipelineViews'

interface PagerProps {
  offset: number
  pageSize: number
  total: number | null
  hasMore: boolean
  onPrev: () => void
  onNext: () => void
  onPageSizeChange: (size: number) => void
  disabled?: boolean
}

export function Pager({ offset, pageSize, total, hasMore, onPrev, onNext, onPageSizeChange, disabled = false }: PagerProps) {
  const from = offset + 1
  const to = offset + pageSize
  const canPrev = offset > 0
  const canNext = hasMore

  const rangeLabel = total != null
    ? `${from.toLocaleString()}–${Math.min(to, total).toLocaleString()} of ${total.toLocaleString()}`
    : `${from.toLocaleString()}–${to.toLocaleString()}`

  return (
    <div className="oc-pager">
      <label className="oc-pager-label">
        Rows
        <select
          value={pageSize}
          disabled={disabled}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="oc-pager-select"
        >
          {PAGE_SIZE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <button
        type="button"
        onClick={onPrev}
        disabled={disabled || !canPrev}
        className="oc-pager-btn"
        aria-label="Previous page"
      >
        ‹
      </button>
      <span className="oc-pager-range">{rangeLabel}</span>
      <button
        type="button"
        onClick={onNext}
        disabled={disabled || !canNext}
        className="oc-pager-btn"
        aria-label="Next page"
      >
        ›
      </button>
    </div>
  )
}
