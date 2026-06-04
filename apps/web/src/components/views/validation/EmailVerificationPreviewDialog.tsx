import type { EmailVerificationPreviewRead } from '../../../lib/types'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import { Loader2 } from 'lucide-react'

function warningText(code: string): string {
  switch (code) {
    case 'max_batch_size_applied': return 'Only the first 200 actionable contacts will be validated in this batch.'
    case 'fresh_cache_reused': return 'Fresh validation results are reused until they are 30 days old.'
    default: return code.replace(/_/g, ' ')
  }
}

interface EmailVerificationPreviewDialogProps {
  open: boolean
  preview: EmailVerificationPreviewRead | null
  previewSummary: {
    skipped_count: number
    cached_count: number
    paid_validation_count: number
  } | null
  loading: boolean
  error: string
  isConfirming: boolean
  onClose: () => void
  onConfirm: () => void
}

export function EmailVerificationPreviewDialog({
  open,
  preview,
  previewSummary,
  loading,
  error,
  isConfirming,
  onClose,
  onConfirm,
}: EmailVerificationPreviewDialogProps) {
  const confirmDisabled = loading || Boolean(error) || !preview || preview.eligible_count === 0
  const summary = preview ? [
    ['selected_count', 'Selected', preview.selected_count],
    ['eligible_count', 'Eligible', preview.eligible_count],
    ['cached_count', 'Cached', previewSummary?.cached_count ?? preview.cached_count],
    ['paid_validation_count', 'ZeroBounce paid validations', previewSummary?.paid_validation_count ?? preview.paid_validation_count],
    ['skipped_count', 'Skipped', previewSummary?.skipped_count ?? preview.skipped_count],
  ] as const : []

  return (
    <ConfirmDialog
      open={open}
      title="Preview email verification"
      confirmLabel="Run verification"
      cancelLabel="Cancel"
      isConfirming={isConfirming}
      confirmDisabled={confirmDisabled}
      onClose={onClose}
      onConfirm={onConfirm}
    >
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--oc-muted)', fontSize: '0.875rem' }}>
          <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} />
          Building preview
        </div>
      ) : error ? (
        <div style={{ color: 'var(--oc-fail-text)', fontSize: '0.875rem' }}>{error}</div>
      ) : preview ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '0.5rem' }}>
            {summary.map(([key, label, value]) => (
              <div key={key} style={{ border: '1px solid var(--oc-border)', borderRadius: '0.5rem', padding: '0.625rem' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.125rem', fontWeight: 800, color: 'var(--s5)' }}>{value}</div>
                <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>{label}</div>
              </div>
            ))}
          </div>

          <div style={{ border: '1px solid var(--oc-border)', borderRadius: '0.5rem', padding: '0.625rem 0.75rem', fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
            <div style={{ fontWeight: 800, color: 'var(--oc-text)', marginBottom: '0.25rem' }}>Credit preview</div>
            Cached results are reused when fresh. ZeroBounce paid validations run only for eligible contacts without reusable cache.
          </div>

          {Object.keys(preview.skipped_reasons).length > 0 && (
            <div style={{ border: '1px solid var(--oc-border)', borderRadius: '0.5rem', overflow: 'hidden' }}>
              {Object.entries(preview.skipped_reasons).map(([reason, count]) => (
                <div key={reason} style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--oc-border)', fontSize: '0.8125rem' }}>
                  <span style={{ color: 'var(--oc-muted)' }}>{reason.replace(/_/g, ' ')}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, color: 'var(--oc-text)' }}>{count}</span>
                </div>
              ))}
            </div>
          )}

          {preview.warnings.length > 0 && (
            <div style={{ color: 'var(--oc-warn-text)', background: 'var(--oc-warn-bg)', borderRadius: '0.5rem', padding: '0.625rem 0.75rem', fontSize: '0.8125rem' }}>
              {preview.warnings.map(warningText).join(', ')}
            </div>
          )}
        </div>
      ) : null}
    </ConfirmDialog>
  )
}
