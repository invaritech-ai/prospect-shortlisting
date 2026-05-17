import { useState } from 'react'

const COLUMNS = [
  { name: 'URL / Domain', required: true,  example: 'https://linear.app',      note: 'One per row. The only required column.' },
  { name: 'Company Name', required: false, example: 'Linear',                  note: 'Optional — we infer it if missing.' },
  { name: 'Source',       required: false, example: 'LinkedIn outbound',       note: 'Tag to track where the lead came from.' },
]

export function FormatGuide() {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ borderRadius: '0.875rem', border: '1px solid var(--oc-border)', overflow: 'hidden' }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%', padding: '0.875rem 1rem',
          background: 'var(--oc-surface)', border: 'none', cursor: 'pointer',
          fontFamily: 'inherit', textAlign: 'left',
          transition: 'background 160ms',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--oc-surface-dim)' }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--oc-surface)' }}
      >
        <span style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)' }}>
          📄 What format does my file need to be in?
        </span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          style={{ color: 'var(--oc-muted)', flexShrink: 0, transition: 'transform 160ms', transform: open ? 'rotate(180deg)' : 'none' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div style={{ borderTop: '1px solid var(--oc-border)', padding: '1rem', background: 'var(--oc-surface)', display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--oc-muted)', margin: 0, lineHeight: 1.6 }}>
            One company per row. The URL/domain column is the only requirement — everything else is optional.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {COLUMNS.map((col) => (
              <div key={col.name} style={{
                display: 'flex', flexDirection: 'column', gap: '0.125rem',
                padding: '0.625rem 0.75rem', borderRadius: '0.625rem',
                background: 'var(--oc-surface-dim)', border: '1px solid var(--oc-border)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--oc-text)' }}>{col.name}</span>
                  {col.required && (
                    <span style={{ fontSize: '0.5625rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--oc-accent)', background: 'var(--oc-accent-soft)', padding: '0.125rem 0.375rem', borderRadius: '0.25rem' }}>
                      Required
                    </span>
                  )}
                </div>
                <code style={{ fontSize: '0.8125rem', fontFamily: 'var(--font-mono)', color: 'var(--oc-muted)' }}>
                  e.g. {col.example}
                </code>
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>{col.note}</span>
              </div>
            ))}
          </div>

          <p style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', margin: 0 }}>
            Column headers are detected automatically — order doesn't matter.
          </p>
        </div>
      )}
    </div>
  )
}
