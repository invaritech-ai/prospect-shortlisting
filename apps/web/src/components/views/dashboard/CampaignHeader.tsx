interface CampaignHeaderProps {
  campaignName: string
  totalCompanies: number
  lastUpdated: string
  onUploadClick: () => void
}

export function CampaignHeader({ campaignName, totalCompanies, lastUpdated, onUploadClick }: CampaignHeaderProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
      <div>
        <p className="oc-label" style={{ marginBottom: '0.375rem' }}>Active Campaign</p>
        <h1 className="oc-heading-page" style={{ margin: 0 }}>{campaignName}</h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--oc-muted)', marginTop: '0.375rem' }}>
          <strong style={{ color: 'var(--oc-text)', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
            {totalCompanies.toLocaleString()}
          </strong>
          {' '}companies · updated {new Date(lastUpdated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
      <button type="button" onClick={onUploadClick} className="oc-btn oc-btn-secondary oc-btn-sm" style={{ flexShrink: 0 }}>
        + Upload companies
      </button>
    </div>
  )
}
