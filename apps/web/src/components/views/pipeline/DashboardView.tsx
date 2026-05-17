import type { DragEvent, FormEvent } from 'react'
import type { CompanyCounts, IntegrationHealthItem, StatsResponse, ScrapeJobRead, RunRead } from '../../../lib/types'
import { IconUpload } from '../../ui/icons'

function LiveDot({ color }: { color: string }) {
  return (
    <span style={{ position: 'relative', display: 'flex', width: '0.5rem', height: '0.5rem', flexShrink: 0 }}>
      <span style={{ position: 'absolute', display: 'inline-flex', width: '100%', height: '100%', borderRadius: '9999px', backgroundColor: color, opacity: 0.75, animation: 'oc-ping 1.2s cubic-bezier(0,0,0.2,1) infinite' }} />
      <span style={{ position: 'relative', display: 'inline-flex', width: '0.5rem', height: '0.5rem', borderRadius: '9999px', backgroundColor: color }} />
    </span>
  )
}

type PipelineStageView = 's1-scraping' | 's2-ai' | 's3-contacts' | 's4-reveal' | 's5-validation'

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
  onNavigate: (view: PipelineStageView) => void
  onOpenCampaigns: () => void
  onOpenOperations: () => void
  onOpenSettings: () => void
}

interface StageCardDef {
  view: PipelineStageView
  label: string
  stageColor: string
  stageBg: string
  count: number | null
  hint: string
}

const SERVICE_META: Record<string, { initials: string; color: string }> = {
  openrouter: { initials: 'OR', color: 'var(--oc-accent)' },
  snov:       { initials: 'SN', color: 'var(--s3)' },
  apollo:     { initials: 'AP', color: 'var(--s2)' },
  zerobounce: { initials: 'ZB', color: 'var(--s5)' },
}

function formatCredits(n: number | null): string {
  if (n === null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export function DashboardView({
  companyCounts,
  stats,
  recentScrapeJobs,
  recentRuns,
  servicesHealth,
  isLoadingHealth,
  file,
  isUploading,
  isDragActive,
  onSetFile,
  onSetIsDragActive,
  onUpload,
  hasSelectedCampaign,
  onNavigate,
  onOpenCampaigns,
  onOpenOperations,
  onOpenSettings,
}: DashboardViewProps) {
  const cards: StageCardDef[] = [
    { view: 's1-scraping',   label: 'S1 · Scraping',          stageColor: '--s1', stageBg: '--s1-bg', count: companyCounts?.uploaded ?? null,      hint: 'Companies not yet scraped' },
    { view: 's2-ai',         label: 'S2 · AI Decision',       stageColor: '--s2', stageBg: '--s2-bg', count: companyCounts?.scraped ?? null,        hint: 'Scraped, awaiting classification' },
    { view: 's3-contacts',   label: 'S3 · Contact Discovery', stageColor: '--s3', stageBg: '--s3-bg', count: companyCounts?.classified ?? null,     hint: 'Classified, awaiting contact discovery' },
    { view: 's4-reveal',     label: 'S4 · Reveal',            stageColor: '--s4', stageBg: '--s4-bg', count: null,                                  hint: 'Reveal contact emails' },
    { view: 's5-validation', label: 'S5 · Validation',        stageColor: '--s5', stageBg: '--s5-bg', count: companyCounts?.contact_ready ?? null,  hint: 'Contacts fetched, validate emails' },
  ]

  const handleDragOver = (e: DragEvent) => { e.preventDefault(); onSetIsDragActive(true) }
  const handleDragLeave = () => onSetIsDragActive(false)
  const handleDrop = (e: DragEvent) => {
    e.preventDefault(); onSetIsDragActive(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) onSetFile(dropped)
  }

  const hasQueueActivity = !!stats && (
    stats.scrape.running > 0 || stats.scrape.queued > 0 || stats.scrape.stuck_count > 0
    || stats.analysis.running > 0 || stats.analysis.queued > 0 || stats.analysis.stuck_count > 0
    || (stats.contact_fetch?.running ?? 0) > 0 || (stats.contact_fetch?.queued ?? 0) > 0 || (stats.contact_fetch?.stuck_count ?? 0) > 0
    || (stats.validation?.running ?? 0) > 0 || (stats.validation?.queued ?? 0) > 0 || (stats.validation?.stuck_count ?? 0) > 0
  )

  return (
    <div className="space-y-6">
      {!hasSelectedCampaign && (
        <section className="oc-panel" style={{ padding: '1rem' }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--oc-muted)' }}>
            Stage screens are campaign-scoped. Select a campaign first to run S1-S5 flows.
          </p>
          <button
            type="button"
            style={{ marginTop: '0.75rem', borderRadius: '0.75rem', background: 'var(--oc-accent)', padding: '0.5rem 0.75rem', fontSize: '0.75rem', fontWeight: 700, color: '#fff', border: 'none', cursor: 'pointer' }}
            onClick={onOpenCampaigns}
          >
            Select campaign
          </button>
        </section>
      )}

      {/* Services health */}
      <section>
        <h2 className="oc-section-heading">Services</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {isLoadingHealth && !servicesHealth
            ? Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="oc-panel animate-pulse space-y-2 p-3">
                  <div style={{ height: '2rem', width: '2rem', borderRadius: '9999px', background: 'var(--oc-border)' }} />
                  <div style={{ height: '0.75rem', width: '4rem', borderRadius: '0.25rem', background: 'var(--oc-border)' }} />
                  <div style={{ height: '0.75rem', width: '2.5rem', borderRadius: '0.25rem', background: 'var(--oc-border)' }} />
                </div>
              ))
            : (servicesHealth ?? []).map((svc) => {
                const meta = SERVICE_META[svc.provider] ?? { initials: svc.provider.slice(0, 2).toUpperCase(), color: 'var(--oc-muted)' }
                return (
                  <div key={svc.provider} className="oc-panel" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', padding: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '2rem', width: '2rem', borderRadius: '9999px', fontSize: '0.6875rem', fontWeight: 900, color: '#fff', backgroundColor: meta.color }}>
                        {meta.initials}
                      </div>
                      <span
                        style={{
                          borderRadius: '9999px', padding: '0.125rem 0.5rem', fontSize: '0.625rem', fontWeight: 700,
                          backgroundColor: svc.connected ? 'var(--s3-bg)' : 'var(--oc-surface-strong)',
                          color: svc.connected ? 'var(--s3-text)' : 'var(--oc-muted)',
                        }}
                      >
                        {svc.connected ? 'Connected' : 'Disconnected'}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--oc-text)' }}>{svc.label}</p>
                    <p style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
                      {svc.connected
                        ? svc.credits_remaining !== null
                          ? <><span style={{ fontWeight: 600, color: 'var(--oc-text)' }}>{formatCredits(svc.credits_remaining)}</span> credits</>
                          : svc.message || 'Connected'
                        : svc.message || 'Not configured'}
                    </p>
                    {!svc.connected && (
                      <button type="button" onClick={onOpenSettings}
                        style={{ marginTop: 'auto', alignSelf: 'flex-start', fontSize: '0.6875rem', color: 'var(--oc-accent)', textDecoration: 'underline', textUnderlineOffset: '2px', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                        Configure →
                      </button>
                    )}
                  </div>
                )
              })}
        </div>
      </section>

      {/* Pipeline stage cards */}
      <section>
        <h2 className="oc-section-heading">Pipeline</h2>
        <p style={{ marginBottom: '0.75rem', fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
          Use stage cards for focused S1-S5 work. Use Full Pipeline for cross-stage triage and bulk actions.
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {cards.map((card) => {
            const isLive =
              (card.view === 's1-scraping'   && (stats?.scrape?.running ?? 0) > 0) ||
              (card.view === 's2-ai'         && (stats?.analysis?.running ?? 0) > 0) ||
              (card.view === 's3-contacts'   && (stats?.contact_fetch?.running ?? 0) > 0) ||
              (card.view === 's5-validation' && (stats?.validation?.running ?? 0) > 0)
            return (
              <button
                key={card.view}
                type="button"
                onClick={() => { if (!hasSelectedCampaign) { onOpenCampaigns(); return } onNavigate(card.view) }}
                style={{
                  display: 'flex', flexDirection: 'column', gap: '0.5rem',
                  borderRadius: '1rem', border: `1px solid var(${card.stageColor})`,
                  padding: '1rem', textAlign: 'left',
                  backgroundColor: `var(${card.stageBg})`,
                  cursor: 'pointer', transition: 'box-shadow 160ms',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)')}
                onMouseLeave={(e) => (e.currentTarget.style.boxShadow = '')}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                  <span style={{ fontSize: '0.625rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: `var(${card.stageColor})` }}>
                    {card.label}
                  </span>
                  {isLive && <LiveDot color={`var(${card.stageColor})`} />}
                </span>
                <span style={{ fontSize: '1.875rem', fontWeight: 900, fontVariantNumeric: 'tabular-nums', color: `var(${card.stageColor})` }}>
                  {card.count != null ? card.count.toLocaleString() : '—'}
                </span>
                <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>
                  {card.hint}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* Queue activity chips */}
      {hasQueueActivity && stats && (
        <div className="flex flex-wrap items-center gap-3">
          {(['scrape', 'analysis', 'contact_fetch', 'validation'] as const).map((key) => {
            const s = stats[key]
            if (!s || (s.running === 0 && s.queued === 0 && (s.stuck_count ?? 0) === 0)) return null
            const colorMap = { scrape: '--s1', analysis: '--s2', contact_fetch: '--s3', validation: '--s5' } as const
            const c = colorMap[key]
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderRadius: '0.75rem', border: `1px solid var(${c})`, backgroundColor: `var(${c}-bg)`, padding: '0.5rem 0.75rem' }}>
                <LiveDot color={`var(${c})`} />
                <span style={{ fontSize: '0.75rem', fontWeight: 500, color: `var(${c}-text)` }}>
                  {s.running} running · {s.queued} queued · {s.stuck_count ?? 0} stuck
                </span>
              </div>
            )
          })}
          <button
            type="button"
            onClick={onOpenOperations}
            style={{ borderRadius: '0.75rem', border: '1px solid var(--oc-border)', background: 'var(--oc-surface-strong)', padding: '0.5rem 0.75rem', fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-accent-ink)', cursor: 'pointer', transition: 'border-color 160ms' }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--oc-accent)')}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--oc-border)')}
          >
            View in Operations
          </button>
        </div>
      )}

      {/* Upload section */}
      <section>
        <h2 className="oc-section-heading">Add Companies</h2>
        <form onSubmit={onUpload} className="flex flex-col gap-3">
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={isDragActive ? 'oc-upload-zone oc-upload-zone-active' : 'oc-upload-zone'}
          >
            <IconUpload size={24} className="oc-icon-muted" />
            <p style={{ fontSize: '0.875rem', color: 'var(--oc-muted)' }}>
              {file ? file.name : 'Drop a file here, or click to browse (CSV, TXT, XLS, XLSX)'}
            </p>
            <input type="file" accept=".csv,.txt,.xls,.xlsx" className="hidden" id="csv-upload"
              onChange={(e) => onSetFile(e.target.files?.[0] ?? null)} />
            <label htmlFor="csv-upload" className="oc-upload-file-label">Choose file</label>
          </div>
          {file && (
            <button
              type="submit"
              disabled={isUploading}
              className="oc-btn oc-btn-primary oc-btn-md"
              style={{ alignSelf: 'stretch' }}
            >
              {isUploading ? 'Uploading…' : `Upload ${file.name}`}
            </button>
          )}
        </form>
      </section>

      {/* Recent activity */}
      {(recentScrapeJobs.length > 0 || recentRuns.length > 0) && (
        <section>
          <h2 className="oc-section-heading">Recent Activity</h2>
          <div className="space-y-1.5">
            {recentScrapeJobs.slice(0, 3).map((job) => (
              <div key={job.id} className="oc-activity-row">
                <span style={{ width: '4rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 700, color: 'var(--s1)' }}>S1</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--oc-text)' }}>{job.domain}</span>
                <span style={{ color: 'var(--oc-muted)' }}>{job.state}</span>
              </div>
            ))}
            {recentRuns.slice(0, 3).map((run) => (
              <div key={run.id} className="oc-activity-row">
                <span style={{ width: '4rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 700, color: 'var(--s2)' }}>S2</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--oc-text)' }}>{run.prompt_name ?? 'Run'}</span>
                <span style={{ color: 'var(--oc-muted)' }}>{run.status}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
