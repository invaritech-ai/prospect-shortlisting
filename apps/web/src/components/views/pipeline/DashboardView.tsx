import type { FormEvent } from 'react'
import type { CompanyCounts, IntegrationHealthItem, StatsResponse, ScrapeJobRead, RunRead } from '../../../lib/types'
import { MOCK_COMPANY_COUNTS, MOCK_STATS, MOCK_RECENT_SCRAPE_JOBS, MOCK_RECENT_RUNS, MOCK_SERVICES_HEALTH, MOCK_ACTIVE_CAMPAIGN, buildFunnelSummary } from '../../../lib/useAppData'
import { CampaignHeader }  from '../dashboard/CampaignHeader'
import { PipelineFunnel }  from '../dashboard/PipelineFunnel'
import { StageCards }      from '../dashboard/StageCards'
import { AttentionItems }  from '../dashboard/AttentionItems'
import type { AttentionItem } from '../dashboard/AttentionItems'
import { ServicesHealth }  from '../dashboard/ServicesHealth'
import { RecentActivity }  from '../dashboard/RecentActivity'
import { UploadZone }      from '../dashboard/UploadZone'

type PipelineStageView = 's1-scraping' | 's2-ai' | 's3-contacts' | 's5-validation'

interface DashboardViewProps {
  companyCounts: CompanyCounts | null
  stats: StatsResponse | null
  recentScrapeJobs: ScrapeJobRead[]
  recentRuns: RunRead[]
  servicesHealth: IntegrationHealthItem[] | null
  isLoadingHealth: boolean
  file: File | null
  isUploading: boolean
  isDragActive: boolean
  onSetFile: (f: File | null) => void
  onSetIsDragActive: (v: boolean) => void
  onUpload: (e: FormEvent) => void
  hasSelectedCampaign: boolean
  activeCampaignName?: string | null
  onNavigate: (view: PipelineStageView) => void
  onOpenCampaigns: () => void
  onOpenOperations: () => void
  onOpenSettings: () => void
}

export function DashboardView({
  companyCounts: rawCounts,
  stats: rawStats,
  recentScrapeJobs: rawScrapeJobs,
  recentRuns: rawRuns,
  servicesHealth: rawHealth,
  isLoadingHealth,
  file, isUploading, isDragActive,
  onSetFile, onSetIsDragActive, onUpload,
  hasSelectedCampaign,
  activeCampaignName,
  onNavigate, onOpenCampaigns, onOpenOperations, onOpenSettings,
}: DashboardViewProps) {
  // Fall back to mock data while backend isn't wired
  const counts     = rawCounts ?? MOCK_COMPANY_COUNTS
  const stats      = rawStats  ?? MOCK_STATS
  const scrapeJobs = rawScrapeJobs.length ? rawScrapeJobs : MOCK_RECENT_SCRAPE_JOBS
  const runs       = rawRuns.length       ? rawRuns       : MOCK_RECENT_RUNS
  const health     = rawHealth            ?? MOCK_SERVICES_HEALTH
  const campaign   = activeCampaignName   ?? MOCK_ACTIVE_CAMPAIGN.name

  const funnel = buildFunnelSummary(counts, stats)

  // Attention items — only show what's actually actionable
  const attentionItems: AttentionItem[] = [
    counts.unknown > 0 && {
      key: 'unknown', color: 'var(--s2)', bg: 'var(--s2-bg)', icon: '◎',
      text: `${counts.unknown.toLocaleString()} companies marked Unknown — do they look promising?`,
      action: 'Review now', onAction: () => onNavigate('s2-ai'),
    },
    stats.scrape.stuck_count > 0 && {
      key: 'stuck', color: 'var(--oc-fail-text)', bg: 'var(--oc-fail-bg)', icon: '⚠',
      text: `${stats.scrape.stuck_count} scrape jobs appear stuck`,
      action: 'View jobs', onAction: () => onNavigate('s1-scraping'),
    },
    counts.contact_ready > 0 && !stats.contact_fetch?.running && !stats.contact_fetch?.queued && {
      key: 'contacts', color: 'var(--s3)', bg: 'var(--s3-bg)', icon: '→',
      text: `${counts.contact_ready.toLocaleString()} Possible companies waiting for contact discovery`,
      action: 'Fetch contacts', onAction: () => onNavigate('s3-contacts'),
    },
    stats.validation && !stats.validation.running && !stats.validation.queued && funnel.contactsFound > funnel.validEmails && {
      key: 'validation', color: 'var(--s5)', bg: 'var(--s5-bg)', icon: '✓',
      text: `${(funnel.contactsFound - funnel.validEmails).toLocaleString()} email addresses waiting to be validated`,
      action: 'Validate', onAction: () => onNavigate('s5-validation'),
    },
  ].filter(Boolean) as AttentionItem[]

  const stageCards = [
    {
      view: 's1-scraping' as const, stageNum: 'S1', label: 'Scraping',
      color: 'var(--s1)', bg: 'var(--s1-bg)', textColor: 'var(--s1-text)', glow: 'var(--s1-glow)',
      count: counts.uploaded, hint: counts.uploaded === 0 ? 'All caught up' : 'pending',
      isLive: stats.scrape.running > 0, liveLabel: `${stats.scrape.running} running`,
    },
    {
      view: 's2-ai' as const, stageNum: 'S2', label: 'AI Review',
      color: 'var(--s2)', bg: 'var(--s2-bg)', textColor: 'var(--s2-text)', glow: 'var(--s2-glow)',
      count: counts.unknown, hint: counts.unknown === 0 ? 'Nothing to review' : 'need your review',
      isLive: (stats.analysis?.running ?? 0) > 0, liveLabel: `${stats.analysis?.running ?? 0} running`,
    },
    {
      view: 's3-contacts' as const, stageNum: 'S3', label: 'Contacts',
      color: 'var(--s3)', bg: 'var(--s3-bg)', textColor: 'var(--s3-text)', glow: 'var(--s3-glow)',
      count: counts.contact_ready, hint: counts.contact_ready === 0 ? 'All caught up' : 'awaiting discovery',
      isLive: (stats.contact_fetch?.running ?? 0) > 0, liveLabel: `${stats.contact_fetch?.running ?? 0} running`,
    },
    {
      view: 's5-validation' as const, stageNum: 'S4', label: 'Validation',
      color: 'var(--s5)', bg: 'var(--s5-bg)', textColor: 'var(--s5-text)', glow: 'var(--s5-glow)',
      count: stats.validation ? (stats.validation.total - stats.validation.succeeded - stats.validation.failed) : 0,
      hint: 'emails to verify',
      isLive: (stats.validation?.running ?? 0) > 0, liveLabel: `${stats.validation?.running ?? 0} running`,
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', paddingBottom: '2rem' }}>
      <CampaignHeader
        campaignName={campaign}
        totalCompanies={counts.total}
        lastUpdated={stats.as_of}
        onUploadClick={() => {}}
      />
      <PipelineFunnel funnel={funnel} />
      <StageCards cards={stageCards} hasSelectedCampaign={hasSelectedCampaign} onNavigate={onNavigate} onOpenCampaigns={onOpenCampaigns} />
      <AttentionItems items={attentionItems} />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <ServicesHealth services={health} isLoading={isLoadingHealth} onOpenSettings={onOpenSettings} />
        <RecentActivity scrapeJobs={scrapeJobs} runs={runs} onViewAll={onOpenOperations} />
      </div>
      <UploadZone file={file} isUploading={isUploading} isDragActive={isDragActive} onSetFile={onSetFile} onSetIsDragActive={onSetIsDragActive} onUpload={onUpload} />
    </div>
  )
}
