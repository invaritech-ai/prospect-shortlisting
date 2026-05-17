import type { FormEvent, DragEvent } from 'react'
import type {
  CompanyCounts,
  IntegrationHealthItem,
  StatsResponse,
  ScrapeJobRead,
  RunRead,
} from '../../../lib/types'
import type { FunnelSummary } from '../../../lib/mockData'
import {
  MOCK_COMPANY_COUNTS,
  MOCK_STATS,
  MOCK_RECENT_SCRAPE_JOBS,
  MOCK_RECENT_RUNS,
  MOCK_SERVICES_HEALTH,
  MOCK_ACTIVE_CAMPAIGN,
  buildFunnelSummary,
} from '../../../lib/mockData'
import { IconUpload } from '../../ui/icons'

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

// ── Sub-components ──────────────────────────────────────────────

function LiveDot({ color }: { color: string }) {
  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: '0.5rem', height: '0.5rem', flexShrink: 0 }}>
      <span style={{ position: 'absolute', inset: 0, borderRadius: '9999px', backgroundColor: color, opacity: 0.5, animation: 'oc-ping 1.4s cubic-bezier(0,0,0.2,1) infinite' }} />
      <span style={{ position: 'relative', width: '0.5rem', height: '0.5rem', borderRadius: '9999px', backgroundColor: color }} />
    </span>
  )
}

function FunnelStep({
  label, value, subLabel, color, isLast = false,
}: {
  label: string
  value: number
  subLabel?: string
  color: string
  isLast?: boolean
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, flex: 1, minWidth: 0 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 'clamp(1.375rem, 3vw, 2rem)',
          fontWeight: 700, letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums',
          color, lineHeight: 1,
        }}>
          {value.toLocaleString()}
        </div>
        <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-text)', marginTop: '0.25rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {label}
        </div>
        {subLabel && (
          <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>
            {subLabel}
          </div>
        )}
      </div>
      {!isLast && (
        <div style={{ padding: '0 0.5rem', color: 'var(--oc-border)', fontSize: '1.125rem', flexShrink: 0, alignSelf: 'center', paddingBottom: '1.25rem' }}>
          →
        </div>
      )}
    </div>
  )
}

const SERVICE_META: Record<string, { initials: string; colorVar: string }> = {
  openrouter: { initials: 'OR', colorVar: 'var(--oc-accent)' },
  apollo:     { initials: 'AP', colorVar: 'var(--s3)' },
  snov:       { initials: 'SN', colorVar: 'var(--s3)' },
  zerobounce: { initials: 'ZB', colorVar: 'var(--s5)' },
}

function formatCredits(n: number | null, message?: string): string {
  if (message) return message
  if (n === null) return 'Connected'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M credits`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k credits`
  return `${n.toLocaleString()} credits`
}

function pct(a: number, b: number): string {
  if (!b) return '—'
  return `${Math.round((a / b) * 100)}%`
}

// ── Main component ───────────────────────────────────────────────

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
  const counts        = rawCounts   ?? MOCK_COMPANY_COUNTS
  const stats         = rawStats    ?? MOCK_STATS
  const scrapeJobs    = rawScrapeJobs.length ? rawScrapeJobs : MOCK_RECENT_SCRAPE_JOBS
  const runs          = rawRuns.length       ? rawRuns       : MOCK_RECENT_RUNS
  const health        = rawHealth   ?? MOCK_SERVICES_HEALTH
  const campaignName  = activeCampaignName   ?? MOCK_ACTIVE_CAMPAIGN.name

  const funnel: FunnelSummary = buildFunnelSummary(counts, stats)

  const handleDragOver  = (e: DragEvent) => { e.preventDefault(); onSetIsDragActive(true) }
  const handleDragLeave = () => onSetIsDragActive(false)
  const handleDrop = (e: DragEvent) => {
    e.preventDefault(); onSetIsDragActive(false)
    const f = e.dataTransfer.files[0]
    if (f) onSetFile(f)
  }

  // Attention items — things that need the user's action
  const attentionItems = [
    counts.unknown > 0 && {
      key: 'unknown',
      color: 'var(--s2)',
      bg: 'var(--s2-bg)',
      icon: '◎',
      text: `${counts.unknown.toLocaleString()} companies marked Unknown — do they look promising?`,
      action: 'Review now',
      onAction: () => onNavigate('s2-ai'),
    },
    stats.scrape.stuck_count > 0 && {
      key: 'stuck',
      color: 'var(--oc-fail-text)',
      bg: 'var(--oc-fail-bg)',
      icon: '⚠',
      text: `${stats.scrape.stuck_count} scrape jobs appear stuck`,
      action: 'View jobs',
      onAction: () => onNavigate('s1-scraping'),
    },
    counts.contact_ready > 0 && stats.contact_fetch && stats.contact_fetch.queued === 0 && stats.contact_fetch.running === 0 && {
      key: 'contacts',
      color: 'var(--s3)',
      bg: 'var(--s3-bg)',
      icon: '→',
      text: `${counts.contact_ready.toLocaleString()} Possible companies waiting for contact discovery`,
      action: 'Fetch contacts',
      onAction: () => onNavigate('s3-contacts'),
    },
    stats.validation && stats.validation.queued === 0 && stats.validation.running === 0 && funnel.contactsFound > funnel.validEmails && {
      key: 'validation',
      color: 'var(--s5)',
      bg: 'var(--s5-bg)',
      icon: '✓',
      text: `${(funnel.contactsFound - funnel.validEmails).toLocaleString()} email addresses waiting to be validated`,
      action: 'Validate emails',
      onAction: () => onNavigate('s5-validation'),
    },
  ].filter(Boolean) as Array<{ key: string; color: string; bg: string; icon: string; text: string; action: string; onAction: () => void }>

  const stageCards = [
    {
      view: 's1-scraping' as const,
      stageNum: 'S1', label: 'Scraping',
      description: 'Fetch & parse websites',
      color: 'var(--s1)', bg: 'var(--s1-bg)', textColor: 'var(--s1-text)', glow: 'var(--s1-glow)',
      count: counts.uploaded,
      hint: counts.uploaded === 0 ? 'All caught up' : 'pending',
      isLive: stats.scrape.running > 0,
      liveLabel: `${stats.scrape.running} running`,
    },
    {
      view: 's2-ai' as const,
      stageNum: 'S2', label: 'AI Review',
      description: 'Classify with LLM',
      color: 'var(--s2)', bg: 'var(--s2-bg)', textColor: 'var(--s2-text)', glow: 'var(--s2-glow)',
      count: counts.unknown,
      hint: counts.unknown === 0 ? 'Nothing to review' : 'need your review',
      isLive: (stats.analysis?.running ?? 0) > 0,
      liveLabel: `${stats.analysis?.running ?? 0} running`,
    },
    {
      view: 's3-contacts' as const,
      stageNum: 'S3', label: 'Contacts',
      description: 'Discover & reveal emails',
      color: 'var(--s3)', bg: 'var(--s3-bg)', textColor: 'var(--s3-text)', glow: 'var(--s3-glow)',
      count: counts.contact_ready,
      hint: counts.contact_ready === 0 ? 'All caught up' : 'awaiting discovery',
      isLive: (stats.contact_fetch?.running ?? 0) > 0,
      liveLabel: `${stats.contact_fetch?.running ?? 0} running`,
    },
    {
      view: 's5-validation' as const,
      stageNum: 'S5', label: 'Validation',
      description: 'Verify deliverability',
      color: 'var(--s5)', bg: 'var(--s5-bg)', textColor: 'var(--s5-text)', glow: 'var(--s5-glow)',
      count: stats.validation ? (stats.validation.total - stats.validation.succeeded - stats.validation.failed) : 0,
      hint: 'emails to verify',
      isLive: (stats.validation?.running ?? 0) > 0,
      liveLabel: `${stats.validation?.running ?? 0} running`,
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', paddingBottom: '2rem' }}>

      {/* ── Campaign header ────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
        <div>
          <p className="oc-label" style={{ marginBottom: '0.375rem' }}>Active Campaign</p>
          <h1 className="oc-heading-page" style={{ margin: 0 }}>{campaignName}</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--oc-muted)', marginTop: '0.375rem' }}>
            <strong style={{ color: 'var(--oc-text)', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
              {counts.total.toLocaleString()}
            </strong>
            {' '}companies · last updated {new Date(stats.as_of).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        <button type="button" onClick={() => {}} className="oc-btn oc-btn-secondary oc-btn-sm" style={{ flexShrink: 0 }}>
          + Upload companies
        </button>
      </div>

      {/* ── Pipeline funnel ────────────────────────────────── */}
      <div className="oc-panel" style={{ padding: '1.5rem' }}>
        <p className="oc-label" style={{ marginBottom: '1.25rem' }}>Pipeline Progress</p>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0, overflowX: 'auto' }}>
          <FunnelStep
            label="Uploaded"
            value={funnel.uploaded}
            subLabel="starting point"
            color="var(--oc-muted)"
          />
          <FunnelStep
            label="Scraped"
            value={funnel.scraped}
            subLabel={pct(funnel.scraped, funnel.uploaded)}
            color="var(--s1)"
          />
          <FunnelStep
            label="Possible"
            value={funnel.possible}
            subLabel={pct(funnel.possible, funnel.uploaded)}
            color="var(--s2)"
          />
          <FunnelStep
            label="Contacts Found"
            value={funnel.contactsFound}
            subLabel={`${pct(funnel.contactsFound, funnel.possible)} of Possible`}
            color="var(--s3)"
          />
          <FunnelStep
            label="Valid Emails"
            value={funnel.validEmails}
            subLabel={`${pct(funnel.validEmails, funnel.contactsFound)} delivery rate`}
            color="var(--s5)"
            isLast
          />
        </div>

        {/* Progress bar */}
        <div style={{ marginTop: '1.25rem', height: '0.375rem', borderRadius: '9999px', background: 'var(--oc-border)', overflow: 'hidden' }}>
          <div style={{
            height: '100%', borderRadius: '9999px',
            width: `${pct(funnel.validEmails, funnel.uploaded)}`,
            background: 'linear-gradient(90deg, var(--s1), var(--s2), var(--s3), var(--s5))',
            transition: 'width 600ms ease',
          }} />
        </div>
        <p style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.5rem', textAlign: 'right' }}>
          {pct(funnel.validEmails, funnel.uploaded)} end-to-end conversion
        </p>
      </div>

      {/* ── Stage cards ────────────────────────────────────── */}
      <section>
        <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Stages</p>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {stageCards.map((card) => (
            <button
              key={card.view}
              type="button"
              onClick={() => { if (!hasSelectedCampaign) { onOpenCampaigns(); return } onNavigate(card.view) }}
              className="oc-stage-card"
              style={{
                backgroundColor: card.bg,
                borderColor: `color-mix(in srgb, ${card.color} 28%, white)`,
                '--card-glow': card.glow,
              } as React.CSSProperties}
            >
              {/* Stage number + live dot */}
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.18em', color: card.color }}>
                  {card.stageNum}
                </span>
                {card.isLive && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.625rem', fontWeight: 600, color: card.color }}>
                    <LiveDot color={card.color} />
                    {card.liveLabel}
                  </span>
                )}
              </span>

              {/* Big count */}
              <span style={{
                fontFamily: 'var(--font-mono)', fontWeight: 700,
                fontSize: 'clamp(2rem, 5vw, 2.75rem)', lineHeight: 1,
                letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums',
                color: card.color,
              }}>
                {card.count.toLocaleString()}
              </span>

              {/* Label */}
              <span>
                <span style={{ display: 'block', fontWeight: 700, fontSize: '1rem', color: card.textColor, lineHeight: 1.2 }}>
                  {card.label}
                </span>
                <span style={{ display: 'block', fontSize: '0.75rem', color: card.color, opacity: 0.7, marginTop: '0.2rem' }}>
                  {card.hint}
                </span>
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* ── Needs attention ────────────────────────────────── */}
      {attentionItems.length > 0 && (
        <section>
          <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Needs Your Attention</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {attentionItems.map((item) => (
              <div key={item.key} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: '1rem', borderRadius: '0.875rem', padding: '0.875rem 1rem',
                backgroundColor: item.bg,
                border: `1px solid color-mix(in srgb, ${item.color} 20%, white)`,
                borderLeft: `3px solid ${item.color}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
                  <span style={{ fontSize: '0.875rem', fontWeight: 700, color: item.color, flexShrink: 0 }}>{item.icon}</span>
                  <p style={{ margin: 0, fontSize: '0.9375rem', color: 'var(--oc-text)', lineHeight: 1.4 }}>{item.text}</p>
                </div>
                <button
                  type="button"
                  onClick={item.onAction}
                  className="oc-btn oc-btn-secondary oc-btn-sm"
                  style={{ flexShrink: 0, borderColor: `color-mix(in srgb, ${item.color} 30%, white)`, color: item.color }}
                >
                  {item.action} →
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Bottom row: Services + Activity ───────────────── */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">

        {/* Connected services */}
        <section>
          <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Services</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {(isLoadingHealth && !health.length
              ? Array.from({ length: 4 }).map((_, i) => ({ id: `skel-${i}` }))
              : health
            ).map((svc: any) => {
              if ('id' in svc && svc.id?.startsWith('skel')) {
                return (
                  <div key={svc.id} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.625rem 0.875rem', borderRadius: '0.75rem', background: 'var(--oc-surface-dim)' }}>
                    <div className="oc-skeleton" style={{ width: '2rem', height: '2rem', borderRadius: '0.5rem' }} />
                    <div className="oc-skeleton" style={{ width: '40%', height: '0.75rem' }} />
                    <div className="oc-skeleton" style={{ width: '25%', height: '0.75rem', marginLeft: 'auto' }} />
                  </div>
                )
              }
              const item = svc as IntegrationHealthItem
              const meta = SERVICE_META[item.provider] ?? { initials: item.provider.slice(0,2).toUpperCase(), colorVar: 'var(--oc-muted)' }
              return (
                <div key={item.provider} style={{
                  display: 'flex', alignItems: 'center', gap: '0.75rem',
                  padding: '0.75rem 0.875rem', borderRadius: '0.75rem',
                  background: 'var(--oc-surface)',
                  border: '1px solid var(--oc-border)',
                  transition: 'box-shadow 160ms',
                }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    width: '2rem', height: '2rem', borderRadius: '0.5rem', flexShrink: 0,
                    background: `color-mix(in srgb, ${meta.colorVar} 12%, white)`,
                    fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 700,
                    color: meta.colorVar,
                  }}>
                    {meta.initials}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)' }}>{item.label}</span>
                  </div>
                  <div style={{ flexShrink: 0, textAlign: 'right' }}>
                    {item.connected ? (
                      <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
                        {formatCredits(item.credits_remaining, item.message || undefined)}
                      </span>
                    ) : (
                      <button type="button" onClick={onOpenSettings}
                        style={{ fontSize: '0.8125rem', color: 'var(--oc-fail-text)', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit' }}>
                        Not configured →
                      </button>
                    )}
                  </div>
                  <div style={{ width: '0.5rem', height: '0.5rem', borderRadius: '9999px', flexShrink: 0, backgroundColor: item.connected ? 'var(--oc-success-text)' : 'var(--oc-border)' }} />
                </div>
              )
            })}
          </div>
        </section>

        {/* Recent activity */}
        <section>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.875rem' }}>
            <p className="oc-label" style={{ margin: 0 }}>Recent Activity</p>
            <button type="button" onClick={onOpenOperations}
              style={{ fontSize: '0.75rem', color: 'var(--oc-accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit', fontWeight: 500 }}>
              View all →
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {scrapeJobs.slice(0, 2).map((job) => (
              <div key={job.id} className="oc-activity-row">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 700, color: 'var(--s1)', flexShrink: 0 }}>S1</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.9375rem', color: 'var(--oc-text)' }}>{job.domain}</span>
                <span style={{
                  fontSize: '0.75rem', fontWeight: 600, flexShrink: 0,
                  color: job.state === 'done' ? 'var(--oc-success-text)' : job.state === 'failed' ? 'var(--oc-fail-text)' : 'var(--oc-muted)',
                }}>
                  {job.state}
                </span>
              </div>
            ))}
            {runs.slice(0, 2).map((run) => (
              <div key={run.id} className="oc-activity-row">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 700, color: 'var(--s2)', flexShrink: 0 }}>S2</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.9375rem', color: 'var(--oc-text)' }}>{run.prompt_name}</span>
                <span style={{
                  fontSize: '0.75rem', fontWeight: 600, flexShrink: 0,
                  color: run.status === 'done' ? 'var(--oc-success-text)' : run.status === 'running' ? 'var(--s2)' : 'var(--oc-muted)',
                }}>
                  {run.status === 'running' ? `${run.completed_jobs}/${run.total_jobs}` : run.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* ── Upload section ─────────────────────────────────── */}
      <section>
        <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Add More Companies</p>
        <form onSubmit={onUpload} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={isDragActive ? 'oc-upload-zone oc-upload-zone-active' : 'oc-upload-zone'}
          >
            <IconUpload size={24} className="oc-icon-muted" />
            <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', margin: 0, textAlign: 'center' }}>
              {file
                ? <><strong style={{ color: 'var(--oc-text)', fontWeight: 600 }}>{file.name}</strong> — ready to upload</>
                : 'Drop a CSV, TXT, XLS, or XLSX file here'}
            </p>
            <input type="file" accept=".csv,.txt,.xls,.xlsx" className="hidden" id="csv-upload"
              onChange={(e) => onSetFile(e.target.files?.[0] ?? null)} />
            <label htmlFor="csv-upload" className="oc-upload-file-label">Browse files</label>
          </div>
          {file && (
            <button type="submit" disabled={isUploading} className="oc-btn oc-btn-primary oc-btn-md">
              {isUploading ? 'Uploading…' : `Upload ${file.name}`}
            </button>
          )}
        </form>
      </section>

    </div>
  )
}
