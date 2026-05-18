import { useState } from 'react'

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
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)' }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--oc-muted)', flexShrink: 0 }}>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
            <line x1="10" y1="9" x2="8" y2="9"/>
          </svg>
          What format does my file need to be in?
        </span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          style={{ color: 'var(--oc-muted)', flexShrink: 0, transition: 'transform 160ms', transform: open ? 'rotate(180deg)' : 'none' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div style={{ borderTop: '1px solid var(--oc-border)', padding: '1rem', background: 'var(--oc-surface)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--oc-muted)', margin: 0, lineHeight: 1.6 }}>
            One company URL per row. Extra columns (company name, tags, etc.) are ignored — only the URL is imported.
          </p>
          <div style={{
            padding: '0.625rem 0.75rem', borderRadius: '0.625rem',
            background: 'var(--oc-surface-dim)', border: '1px solid var(--oc-border)',
            display: 'flex', flexDirection: 'column', gap: '0.25rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--oc-text)' }}>URL / Domain</span>
              <span style={{ fontSize: '0.5625rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--oc-accent)', background: 'var(--oc-accent-soft)', padding: '0.125rem 0.375rem', borderRadius: '0.25rem' }}>
                Required
              </span>
            </div>
            <code style={{ fontSize: '0.8125rem', fontFamily: 'var(--font-mono)', color: 'var(--oc-muted)' }}>
              e.g. https://linear.app
            </code>
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
              Any cell per row that looks like a URL is detected automatically — no header required.
            </span>
          </div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', margin: 0 }}>
            Duplicate domains within the same campaign are skipped automatically.
          </p>
        </div>
      )}
    </div>
  )
}
