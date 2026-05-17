import type { ManualLabel } from '../../lib/types'

const LABEL_OPTIONS: Array<{ value: ManualLabel; short: string; title: string; activeStyle: React.CSSProperties; inactiveStyle: React.CSSProperties }> = [
  {
    value: 'possible', short: 'P', title: 'Mark as Possible',
    activeStyle:   { background: 'var(--oc-success-bg)', color: 'var(--oc-success-text)', borderColor: 'var(--oc-success-text)' },
    inactiveStyle: { background: 'var(--oc-success-bg)', color: 'var(--oc-success-text)', borderColor: 'color-mix(in srgb, var(--oc-success-text) 30%, white)', opacity: 0.5 },
  },
  {
    value: 'unknown', short: 'U', title: 'Mark as Unknown',
    activeStyle:   { background: 'var(--oc-surface)', color: 'var(--oc-muted)', borderColor: 'var(--oc-border)' },
    inactiveStyle: { background: 'var(--oc-surface)', color: 'var(--oc-muted)', borderColor: 'var(--oc-border)', opacity: 0.5 },
  },
  {
    value: 'crap', short: 'C', title: 'Mark as Crap',
    activeStyle:   { background: 'var(--oc-fail-bg)', color: 'var(--oc-fail-text)', borderColor: 'var(--oc-fail-text)' },
    inactiveStyle: { background: 'var(--oc-fail-bg)', color: 'var(--oc-fail-text)', borderColor: 'color-mix(in srgb, var(--oc-fail-text) 30%, white)', opacity: 0.5 },
  },
]

interface QuickLabelPickerProps {
  current: ManualLabel | null
  disabled?: boolean
  onSelect: (label: ManualLabel | null) => void
}

export function QuickLabelPicker({ current, disabled = false, onSelect }: QuickLabelPickerProps) {
  return (
    <span style={{ marginLeft: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.125rem' }}>
      {LABEL_OPTIONS.map(({ value, short, title, activeStyle, inactiveStyle }) => (
        <button
          key={value}
          type="button"
          title={current === value ? `Remove manual label (${value})` : title}
          aria-label={current === value ? `Remove manual label ${value}` : title}
          disabled={disabled}
          onClick={(e) => { e.stopPropagation(); onSelect(current === value ? null : value) }}
          style={{
            height: '1rem', width: '1rem',
            borderRadius: '0.25rem', border: '1px solid',
            fontSize: '0.5625rem', fontWeight: 700, lineHeight: 1,
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'opacity 160ms',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'inherit',
            ...(current === value ? activeStyle : { ...inactiveStyle, opacity: disabled ? 0.4 : undefined }),
            ...(disabled ? { opacity: 0.4 } : {}),
          }}
        >
          {short}
        </button>
      ))}
    </span>
  )
}
