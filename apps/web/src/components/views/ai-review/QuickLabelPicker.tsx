import type { AIVerdict } from '../../../lib/types'

const OPTIONS: { verdict: AIVerdict; color: string; bg: string; label: string }[] = [
  { verdict: 'Possible', color: 'var(--s2-text)', bg: 'var(--s2-bg)',        label: 'Possible' },
  { verdict: 'Unknown',  color: 'var(--oc-warn-text)', bg: 'var(--oc-warn-bg)', label: 'Unknown'  },
  { verdict: 'Crap',     color: 'var(--oc-fail-text)', bg: 'var(--oc-fail-bg)', label: 'Crap'     },
]

interface QuickLabelPickerProps {
  current: AIVerdict
  onChange: (verdict: AIVerdict) => void
}

export function QuickLabelPicker({ current, onChange }: QuickLabelPickerProps) {
  return (
    <div style={{ display: 'flex', gap: '0.25rem' }}>
      {OPTIONS.map((opt) => {
        const isActive = opt.verdict === current
        return (
          <button
            key={opt.verdict}
            type="button"
            onClick={() => onChange(opt.verdict)}
            style={{
              padding: '0.25rem 0.625rem',
              borderRadius: '9999px',
              fontFamily: 'var(--font-body)',
              fontSize: '0.6875rem',
              fontWeight: 600,
              cursor: 'pointer',
              border: isActive ? `1.5px solid ${opt.color}` : '1.5px solid transparent',
              color: isActive ? opt.color : 'var(--oc-muted)',
              backgroundColor: isActive ? opt.bg : 'transparent',
              transition: 'all 160ms',
              whiteSpace: 'nowrap',
            }}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
