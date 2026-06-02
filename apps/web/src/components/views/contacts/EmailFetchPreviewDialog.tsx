import type { EmailFetchPreviewRead } from '../../../lib/types'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import { Loader2 } from 'lucide-react'

function warningText(code: string): string {
  switch (code) {
    case 'no_include_title_criteria': return 'Add include title rules before fetching.'
    case 'no_apollo_title_matches': return 'Apollo found no title matches in preview.'
    default: return code.replace(/_/g, ' ')
  }
}

interface EmailFetchPreviewDialogProps {
  open: boolean
  preview: EmailFetchPreviewRead | null
  loading: boolean
  error: string
  isConfirming: boolean
  onClose: () => void
  onConfirm: () => void
}

export function EmailFetchPreviewDialog({
  open,
  preview,
  loading,
  error,
  isConfirming,
  onClose,
  onConfirm,
}: EmailFetchPreviewDialogProps) {
  const confirmDisabled = loading || Boolean(error) || !preview || preview.selected_domain_count === 0
  const isRefetch = preview?.mode === 'refetch'
  const creditPlan = preview?.credit_plan

  return (
    <ConfirmDialog
      open={open}
      title={isRefetch ? 'Preview contact refetch' : 'Preview contact fetch'}
      confirmLabel={isRefetch ? 'Run refetch' : 'Run fetch'}
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
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '0.5rem' }}>
            {[
              ['Companies', preview.selected_domain_count],
              ['Apollo reveals', creditPlan?.estimated_apollo_reveals ?? preview.estimated_apollo_reveals],
              ['Snov discovery searches', creditPlan?.estimated_snov_discovery_searches ?? 0],
              ['Snov email lookups', creditPlan?.estimated_snov_email_lookups ?? preview.estimated_snov_fallback_min],
            ].map(([label, value]) => (
              <div key={label} style={{ border: '1px solid var(--oc-border)', borderRadius: '0.5rem', padding: '0.625rem' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.125rem', fontWeight: 800, color: 'var(--s3)' }}>{value}</div>
                <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>{label}</div>
              </div>
            ))}
          </div>

          {creditPlan && (
            <div style={{ border: '1px solid var(--oc-border)', borderRadius: '0.5rem', padding: '0.625rem 0.75rem', fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
              <div style={{ fontWeight: 800, color: 'var(--oc-text)', marginBottom: '0.25rem' }}>Estimated paid usage</div>
              Apollo preview is free. Snov can run up to {creditPlan.snov_title_chunks_per_company} discovery searches per company because {creditPlan.title_hint_count} title hints are active. Email lookups run only for title-matched people.
            </div>
          )}

          {preview.warnings.length > 0 && (
            <div style={{ color: 'var(--oc-warn-text)', background: 'var(--oc-warn-bg)', borderRadius: '0.5rem', padding: '0.625rem 0.75rem', fontSize: '0.8125rem' }}>
              {preview.warnings.map(warningText).join(', ')}
            </div>
          )}

          {isRefetch && (
            <div style={{ color: 'var(--oc-warn-text)', background: 'var(--oc-warn-bg)', borderRadius: '0.5rem', padding: '0.625rem 0.75rem', fontSize: '0.8125rem' }}>
              This will search again for completed companies and may use provider credits again.
            </div>
          )}

          <div style={{ maxHeight: '260px', overflow: 'auto', border: '1px solid var(--oc-border)', borderRadius: '0.5rem' }}>
            {preview.domains.map((domain) => (
              <div key={domain.domain_id} style={{ padding: '0.625rem 0.75rem', borderBottom: '1px solid var(--oc-border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '0.8125rem' }}>{domain.domain}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>{domain.matched_candidate_count} matches</span>
                </div>
                {domain.candidates.length > 0 ? (
                  <div style={{ marginTop: '0.375rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    {domain.candidates.map((candidate) => (
                      <div key={`${candidate.provider}:${candidate.provider_person_id}`} style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
                        {`${candidate.first_name} ${candidate.last_name}`.trim() || 'Unknown'} · {candidate.title}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ marginTop: '0.375rem', fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
                    {domain.warnings.map(warningText).join(', ') || 'Apollo found no title matches in preview.'}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </ConfirmDialog>
  )
}
