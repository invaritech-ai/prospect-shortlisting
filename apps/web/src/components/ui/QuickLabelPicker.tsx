import type { ManualLabel } from '../../lib/types'

const LABEL_OPTIONS: Array<{ value: ManualLabel; short: string; title: string; cls: string }> = [
  { value: 'possible', short: 'P', title: 'Mark as Possible', cls: 'text-emerald-700 border-emerald-300 bg-emerald-50 hover:bg-emerald-100' },
  { value: 'unknown', short: 'U', title: 'Mark as Unknown', cls: 'text-slate-600 border-slate-300 bg-slate-50 hover:bg-slate-100' },
  { value: 'crap', short: 'C', title: 'Mark as Crap', cls: 'text-rose-700 border-rose-300 bg-rose-50 hover:bg-rose-100' },
]

interface QuickLabelPickerProps {
  current: ManualLabel | null
  disabled?: boolean
  onSelect: (label: ManualLabel | null) => void
}

export function QuickLabelPicker({ current, disabled = false, onSelect }: QuickLabelPickerProps) {
  return (
    <span className="ml-1 flex items-center gap-0.5">
      {LABEL_OPTIONS.map(({ value, short, title, cls }) => (
        <button
          key={value}
          type="button"
          title={current === value ? `Remove manual label (${value})` : title}
          aria-label={current === value ? `Remove manual label ${value}` : title}
          disabled={disabled}
          onClick={(e) => {
            e.stopPropagation()
            onSelect(current === value ? null : value)
          }}
          className={`h-4 w-4 rounded border text-[9px] font-bold leading-none transition ${
            current === value
              ? `${cls} ring-1 ring-current opacity-100`
              : `${cls} opacity-60 hover:opacity-100`
          } ${disabled ? 'cursor-not-allowed opacity-40 hover:opacity-40' : ''}`}
        >
          {short}
        </button>
      ))}
    </span>
  )
}
