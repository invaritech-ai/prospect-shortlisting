interface EmptyStateProps {
  onCreateCampaign: () => void
}

export function EmptyState({ onCreateCampaign }: EmptyStateProps) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      textAlign: 'center', padding: '4rem 2rem', gap: '1rem',
      border: '2px dashed var(--oc-border)', borderRadius: '1.25rem',
      background: 'var(--oc-surface)',
    }}>
      <div style={{
        width: '3.5rem', height: '3.5rem', borderRadius: '1rem',
        background: 'var(--oc-surface-dim)', border: '1px solid var(--oc-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '1.5rem',
      }}>
        📋
      </div>
      <div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', color: 'var(--oc-text)', margin: '0 0 0.375rem' }}>
          No campaigns yet
        </h2>
        <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', margin: 0, maxWidth: '28rem' }}>
          A campaign groups a batch of companies through the pipeline. Create one to get started.
        </p>
      </div>
      <button type="button" onClick={onCreateCampaign} className="oc-btn oc-btn-primary oc-btn-md" style={{ marginTop: '0.5rem' }}>
        + Create your first campaign
      </button>
    </div>
  )
}
