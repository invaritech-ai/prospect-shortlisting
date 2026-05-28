import { Check } from 'lucide-react'

interface UploadProgressProps {
  status: 'uploading' | 'success'
  filename: string
  rowCount?: number
  onDone: () => void
}

export function UploadProgress({ status, filename, rowCount, onDone }: UploadProgressProps) {
  const isSuccess = status === 'success'

  return (
    <div style={{
      borderRadius: '1.25rem',
      border: `1px solid ${isSuccess ? 'color-mix(in srgb, var(--oc-success-text) 20%, white)' : 'var(--oc-border)'}`,
      background: isSuccess ? 'var(--oc-success-bg)' : 'var(--oc-surface)',
      padding: '2rem 1.5rem',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.25rem',
      textAlign: 'center',
      animation: 'oc-fade-up 200ms cubic-bezier(0.34,1.56,0.64,1)',
    }}>
      {isSuccess ? (
        <>
          {/* Success icon */}
          <div style={{
            width: '3.5rem', height: '3.5rem', borderRadius: '9999px',
            background: 'var(--oc-success-bg)',
            border: '2px solid var(--oc-success-text)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--oc-success-text)',
          }}>
            <Check size={24} strokeWidth={2.5} />
          </div>

          <div>
            <p style={{ fontFamily: 'var(--font-display)', fontSize: '1.375rem', color: 'var(--oc-text)', margin: '0 0 0.375rem' }}>
              Import complete
            </p>
            {rowCount !== undefined && (
              <p style={{ fontSize: '1rem', color: 'var(--oc-muted)', margin: 0 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--oc-success-text)', fontSize: '1.25rem' }}>
                  {rowCount.toLocaleString()}
                </span>{' '}
                companies added to your campaign
              </p>
            )}
          </div>

          <div style={{ display: 'flex', gap: '0.625rem', flexWrap: 'wrap', justifyContent: 'center' }}>
            <button type="button" onClick={onDone} className="oc-btn oc-btn-primary oc-btn-md">
              Start scraping →
            </button>
            <button type="button" onClick={onDone} className="oc-btn oc-btn-secondary oc-btn-md">
              Import another file
            </button>
          </div>
        </>
      ) : (
        <>
          {/* Uploading state */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem', width: '100%' }}>
            <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', margin: 0 }}>
              Uploading <strong style={{ color: 'var(--oc-text)' }}>{filename}</strong>…
            </p>
            {/* Animated progress bar */}
            <div style={{ width: '100%', maxWidth: '20rem', height: '0.375rem', borderRadius: '9999px', background: 'var(--oc-border)', overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: '9999px',
                background: 'linear-gradient(90deg, var(--s1), var(--s2), var(--s3), var(--s5))',
                animation: 'progress-indeterminate 1.4s ease-in-out infinite',
                width: '40%',
              }} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
