import type { IntegrationHealthItem } from '../../../lib/types'
import { ServicesHealth } from '../dashboard/ServicesHealth'

type PipelineStageView = 's1-scraping' | 's2-ai' | 's3-contacts' | 's4-validation'

interface DashboardViewProps {
  servicesHealth: IntegrationHealthItem[] | null
  isLoadingHealth: boolean
  hasSelectedCampaign: boolean
  activeCampaignName?: string | null
  onNavigate: (view: PipelineStageView) => void
  onNavigateToUploads: () => void
  onOpenCampaigns: () => void
  onOpenSettings: () => void
}

const STAGE_LINKS: Array<{
  view: PipelineStageView
  stageNum: string
  label: string
  color: string
  bg: string
  description: string
}> = [
  { view: 's1-scraping',  stageNum: 'S1', label: 'Scraping',   color: 'var(--s1)', bg: 'var(--s1-bg)',  description: 'Scrape company websites' },
  { view: 's2-ai',        stageNum: 'S2', label: 'AI Review',  color: 'var(--s2)', bg: 'var(--s2-bg)',  description: 'Classify companies with AI' },
  { view: 's3-contacts',  stageNum: 'S3', label: 'Contacts',   color: 'var(--s3)', bg: 'var(--s3-bg)',  description: 'Discover decision-maker contacts' },
  { view: 's4-validation',stageNum: 'S4', label: 'Email Verification', color: 'var(--s5)', bg: 'var(--s5-bg)',  description: 'Validate email addresses' },
]

export function DashboardView({
  servicesHealth,
  isLoadingHealth,
  hasSelectedCampaign,
  activeCampaignName,
  onNavigate,
  onNavigateToUploads,
  onOpenCampaigns,
  onOpenSettings,
}: DashboardViewProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
        <div>
          <p className="oc-label" style={{ marginBottom: '0.375rem' }}>
            {hasSelectedCampaign ? 'Active Campaign' : 'Dashboard'}
          </p>
          <h1 className="oc-heading-page" style={{ margin: 0 }}>
            {activeCampaignName ?? 'No campaign selected'}
          </h1>
        </div>
        <button type="button" onClick={onNavigateToUploads} className="oc-btn oc-btn-secondary oc-btn-sm" style={{ flexShrink: 0 }}>
          + Upload companies
        </button>
      </div>

      {!hasSelectedCampaign && (
        <div className="oc-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginBottom: '1rem' }}>
            Select or create a campaign to get started.
          </p>
          <button type="button" onClick={onOpenCampaigns} className="oc-btn oc-btn-primary oc-btn-sm">
            Go to Campaigns
          </button>
        </div>
      )}

      {hasSelectedCampaign && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.75rem' }}>
          {STAGE_LINKS.map((s) => (
            <button
              key={s.view}
              type="button"
              onClick={() => onNavigate(s.view)}
              className="oc-panel"
              style={{
                display: 'flex', flexDirection: 'column', gap: '0.5rem',
                padding: '1.25rem', textAlign: 'left', cursor: 'pointer',
                background: s.bg, border: `1.5px solid color-mix(in srgb, ${s.color} 25%, transparent)`,
                transition: 'border-color 140ms',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = s.color }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = `color-mix(in srgb, ${s.color} 25%, transparent)` }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{
                  fontSize: '0.625rem', fontWeight: 800, letterSpacing: '0.08em',
                  padding: '0.125rem 0.375rem', borderRadius: '0.25rem',
                  background: s.color, color: '#fff',
                }}>{s.stageNum}</span>
                <span style={{ fontSize: '0.9375rem', fontWeight: 700, color: s.color }}>{s.label}</span>
              </div>
              <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>{s.description}</span>
            </button>
          ))}
        </div>
      )}

      {/* Services health */}
      {(servicesHealth || isLoadingHealth) && (
        <ServicesHealth
          services={servicesHealth ?? []}
          isLoading={isLoadingHealth}
          onOpenSettings={onOpenSettings}
        />
      )}

    </div>
  )
}
