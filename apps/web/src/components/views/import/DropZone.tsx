import type { DragEvent } from 'react'

export type DropZoneState = 'idle' | 'dragging' | 'selected'

interface DropZoneProps {
  file: File | null
  state: DropZoneState
  estimatedRows: number | null
  onFileChange: (f: File | null) => void
  onDragStateChange: (dragging: boolean) => void
}

const ACCEPT = '.csv,.txt,.xls,.xlsx'

const FILE_ICON = (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
    <line x1="10" y1="9" x2="8" y2="9" />
  </svg>
)

const CHECK_ICON = (
  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="8 12 11 15 16 9" />
  </svg>
)

export function DropZone({ file, state, estimatedRows, onFileChange, onDragStateChange }: DropZoneProps) {
  function handleDragOver(e: DragEvent) { e.preventDefault(); onDragStateChange(true) }
  function handleDragLeave() { onDragStateChange(false) }
  function handleDrop(e: DragEvent) {
    e.preventDefault()
    onDragStateChange(false)
    const f = e.dataTransfer.files[0]
    if (f) onFileChange(f)
  }

  const isDragging  = state === 'dragging'
  const hasFile     = state === 'selected' && file

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{
        position: 'relative',
        borderRadius: '1.25rem',
        border: `2px dashed ${isDragging ? 'var(--oc-accent)' : hasFile ? 'var(--oc-success-text)' : 'var(--oc-border)'}`,
        background: isDragging
          ? 'var(--oc-accent-soft)'
          : hasFile
          ? 'var(--oc-success-bg)'
          : 'var(--oc-surface)',
        padding: '2.5rem 1.5rem',
        minHeight: '240px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1rem',
        textAlign: 'center',
        transition: 'border-color 160ms, background 160ms',
        cursor: hasFile ? 'default' : 'pointer',
      }}
      onClick={() => { if (!hasFile) document.getElementById('import-file-input')?.click() }}
    >
      {/* Hidden real input */}
      <input
        id="import-file-input"
        type="file"
        accept={ACCEPT}
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null
          onFileChange(f)
          e.target.value = ''
        }}
      />

      {hasFile ? (
        /* ── File selected state ── */
        <>
          <div style={{ color: 'var(--oc-success-text)' }}>{CHECK_ICON}</div>
          <div>
            <p style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', color: 'var(--oc-text)', margin: '0 0 0.375rem', wordBreak: 'break-all' }}>
              {file!.name}
            </p>
            {estimatedRows !== null && (
              <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', margin: 0 }}>
                ~<span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--oc-text)' }}>
                  {estimatedRows.toLocaleString()}
                </span> rows detected
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onFileChange(null) }}
            className="oc-btn oc-btn-secondary oc-btn-sm"
          >
            Change file
          </button>
        </>
      ) : (
        /* ── Empty / dragging state ── */
        <>
          <div style={{ color: isDragging ? 'var(--oc-accent)' : 'var(--oc-muted)', transition: 'color 160ms, transform 160ms', transform: isDragging ? 'translateY(-4px)' : 'none' }}>
            {FILE_ICON}
          </div>
          <div>
            <p style={{ fontFamily: 'var(--font-display)', fontSize: '1.375rem', color: isDragging ? 'var(--oc-accent)' : 'var(--oc-text)', margin: '0 0 0.375rem', transition: 'color 160ms' }}>
              {isDragging ? 'Drop it!' : 'Drop your file here'}
            </p>
            <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', margin: 0 }}>
              or{' '}
              <label htmlFor="import-file-input" style={{ color: 'var(--oc-accent)', fontWeight: 600, cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: '2px' }}
                onClick={(e) => e.stopPropagation()}>
                tap to browse
              </label>
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
            {['CSV', 'XLSX', 'TXT', 'XLS'].map((fmt) => (
              <span key={fmt} style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 700,
                padding: '0.25rem 0.625rem', borderRadius: '0.375rem',
                background: 'var(--oc-surface-dim)', border: '1px solid var(--oc-border)',
                color: 'var(--oc-muted)',
              }}>{fmt}</span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
