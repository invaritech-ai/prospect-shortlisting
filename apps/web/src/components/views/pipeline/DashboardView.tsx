import type { DragEvent, FormEvent } from 'react'
import type { CompanyCounts, IntegrationHealthItem, StatsResponse, ScrapeJobRead, RunRead } from '../../../lib/types'
import { IconUpload } from '../../ui/icons'

/* Live pulse dot using stage color */
function LiveDot({ color }: { color: string }) {
  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: '0.5rem', height: '0.5rem', flexShrink: 0 }}>
      <span style={{ position: 'absolute', inset: 0, borderRadius: '9999px', backgroundColor: color, opacity: 0.55, animation: 'oc-ping 1.4s cubic-bezier(0,0,0.2,1) infinite' }} />
      <span style={{ position: 'relative', width: '0.5rem', height: '0.5rem', borderRadius: '9999px', backgroundColor: color }} />
    </span>
  )
}

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
  onNavigate: (view: PipelineStageView) => void
  onOpenCampaigns: () => void
  onOpenOperations: () => void
  onOpenSettings: () => void
}

interface StageCardDef {
  view: PipelineStageView
  stageNum: string
  label: string
  description: string
  color: string
  bg: string
  textColor: string
  glow: string
  count: number | null
  hint: string
}

const SERVICE_META: Record<string, { initials: string; colorVar: string }> = {
  openrouter: { initials: 'OR', colorVar: 'var(--oc-accent)' },
  snov:       { initials: 'SN', colorVar: 'var(--s3)' },
  apollo:     { initials: 'AP', colorVar: 'var(--s3)' },
  zerobounce: { initials: 'ZB', colorVar: 'var(--s5)' },
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
    {
      view: 's1-scraping',
      stageNum: 'S1', label: 'Scraping',
      description: 'Fetch website content',
      color: 'var(--s1)', bg: 'var(--s1-bg)', textColor: 'var(--s1-text)', glow: 'var(--s1-glow)',
      count: companyCounts?.uploaded ?? null,
      hint: 'companies queued to scrape',
    },
    {
      view: 's2-ai',
      stageNum: 'S2', label: 'AI Decision',
      description: 'Classify with LLM',
      color: 'var(--s2)', bg: 'var(--s2-bg)', textColor: 'var(--s2-text)', glow: 'var(--s2-glow)',
      count: companyCounts?.scraped ?? null,
      hint: 'scraped, awaiting AI review',
    },
    {
      view: 's3-contacts',
      stageNum: 'S3', label: 'Contacts & Email',
      description: 'Discover & reveal contacts',
      color: 'var(--s3)', bg: 'var(--s3-bg)', textColor: 'var(--s3-text)', glow: 'var(--s3-glow)',
      count: companyCounts?.classified ?? null,
      hint: 'classified, contacts pending',
    },
    {
      view: 's5-validation',
      stageNum: 'S5', label: 'Validation',
      description: 'Verify email deliverability',
      color: 'var(--s5)', bg: 'var(--s5-bg)', textColor: 'var(--s5-text)', glow: 'var(--s5-glow)',
      count: companyCounts?.contact_ready ?? null,
      hint: 'contacts ready to validate',
    },
  ]

  const handleDragOver = (e: DragEvent) => { e.preventDefault(); onSetIsDragActive(true) }
  const handleDragLeave = () => onSetIsDragActive(false)
  const handleDrop = (e: DragEvent) => {
    e.preventDefault(); onSetIsDragActive(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) onSetFile(dropped)
  }

  const queueStats = [
    { key: 's1-scraping' as const,   color: 'var(--s1)', bg: 'var(--s1-bg)', textColor: 'var(--s1-text)', label: 'Scraping',  s: stats?.scrape },
    { key: 's2-ai' as const,         color: 'var(--s2)', bg: 'var(--s2-bg)', textColor: 'var(--s2-text)', label: 'AI',        s: stats?.analysis },
    { key: 's3-contacts' as const,   color: 'var(--s3)', bg: 'var(--s3-bg)', textColor: 'var(--s3-text)', label: 'Contacts',  s: stats?.contact_fetch },
    { key: 's5-validation' as const, color: 'var(--s5)', bg: 'var(--s5-bg)', textColor: 'var(--s5-text)', label: 'Validation',s: stats?.validation },
  ].filter(({ s }) => s && (s.running > 0 || s.queued > 0 || (s.stuck_count ?? 0) > 0))

  return (
    <div className="space-y-8">

      {/* Campaign prompt */}
      {!hasSelectedCampaign && (
        <div className="oc-alert-warn" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
          <p style={{ margin: 0, fontWeight: 500 }}>Select a campaign to run pipeline stages.</p>
          <button type="button" onClick={onOpenCampaigns} className="oc-btn oc-btn-secondary oc-btn-sm" style={{ flexShrink: 0 }}>
            Select campaign
          </button>
        </div>
      )}

      {/* ── Pipeline stages — THE hero section ─────────────── */}
      <section>
        <p className="oc-section-heading">Pipeline</p>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
                className="oc-stage-card"
                style={{
                  backgroundColor: card.bg,
                  borderColor: `color-mix(in srgb, ${card.color} 30%, white)`,
                  '--card-glow': card.glow,
                } as React.CSSProperties}
              >
                {/* Eyebrow */}
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{
                    fontFamily: 'var(--font-body)', fontSize: '0.625rem', fontWeight: 800,
                    textTransform: 'uppercase', letterSpacing: '0.18em', color: card.color,
                  }}>
                    {card.stageNum}
                  </span>
                  {isLive && <LiveDot color={card.color} />}
                </span>

                {/* Big number */}
                <span style={{
                  fontFamily: 'var(--font-mono)', fontWeight: 700,
                  fontSize: 'clamp(2rem, 5vw, 3rem)', lineHeight: 1,
                  letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums',
                  color: card.color,
                }}>
                  {card.count != null ? card.count.toLocaleString() : '—'}
                </span>

                {/* Label + desc */}
                <span>
                  <span style={{ display: 'block', fontWeight: 700, fontSize: '0.9375rem', color: card.textColor, lineHeight: 1.2 }}>
                    {card.label}
                  </span>
                  <span style={{ display: 'block', fontSize: '0.75rem', color: card.color, opacity: 0.75, marginTop: '0.125rem' }}>
                    {card.hint}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* ── Active queue chips ────────────────────────────────── */}
      {queueStats.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {queueStats.map(({ key, color, bg, textColor, label, s }) => s && (
            <div key={key} style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              borderRadius: '9999px', border: `1px solid color-mix(in srgb, ${color} 25%, white)`,
              backgroundColor: bg, padding: '0.375rem 0.875rem',
            }}>
              <LiveDot color={color} />
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: textColor }}>
                {label} · {s.running} running · {s.queued} queued
                {(s.stuck_count ?? 0) > 0 && <span style={{ color: 'var(--oc-fail-text)' }}> · {s.stuck_count} stuck</span>}
              </span>
            </div>
          ))}
          <button type="button" onClick={onOpenOperations}
            className="oc-btn oc-btn-ghost oc-btn-sm" style={{ marginLeft: '0.25rem' }}>
            View operations →
          </button>
        </div>
      )}

      {/* ── Services health ───────────────────────────────────── */}
      <section>
        <p className="oc-section-heading">Connected Services</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {isLoadingHealth && !servicesHealth
            ? Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="oc-panel" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <div className="oc-skeleton" style={{ width: '2.5rem', height: '2.5rem', borderRadius: '9999px' }} />
                  <div className="oc-skeleton" style={{ width: '60%', height: '0.875rem' }} />
                  <div className="oc-skeleton" style={{ width: '40%', height: '0.75rem' }} />
                </div>
              ))
            : (servicesHealth ?? []).map((svc) => {
                const meta = SERVICE_META[svc.provider] ?? { initials: svc.provider.slice(0, 2).toUpperCase(), colorVar: 'var(--oc-muted)' }
                return (
                  <div key={svc.provider} className="oc-panel" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
                      <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        width: '2.5rem', height: '2.5rem', borderRadius: '0.75rem',
                        backgroundColor: `color-mix(in srgb, ${meta.colorVar} 14%, white)`,
                        fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 700,
                        color: meta.colorVar, flexShrink: 0,
                      }}>
                        {meta.initials}
                      </div>
                      <span style={{
                        borderRadius: '9999px', padding: '0.1875rem 0.5rem',
                        fontSize: '0.625rem', fontWeight: 700,
                        backgroundColor: svc.connected ? 'var(--oc-success-bg)' : 'var(--oc-surface-dim)',
                        color: svc.connected ? 'var(--oc-success-text)' : 'var(--oc-muted)',
                        border: '1px solid',
                        borderColor: svc.connected
                          ? 'color-mix(in srgb, var(--oc-success-text) 20%, white)'
                          : 'var(--oc-border)',
                      }}>
                        {svc.connected ? '● Online' : '○ Offline'}
                      </span>
                    </div>
                    <div>
                      <p style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)', margin: 0 }}>{svc.label}</p>
                      <p style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', margin: '0.25rem 0 0' }}>
                        {svc.connected
                          ? svc.credits_remaining !== null
                            ? <><strong style={{ color: 'var(--oc-text)', fontWeight: 600 }}>{formatCredits(svc.credits_remaining)}</strong> credits left</>
                            : svc.message || 'Connected'
                          : svc.message || 'Not configured'}
                      </p>
                    </div>
                    {!svc.connected && (
                      <button type="button" onClick={onOpenSettings}
                        style={{ marginTop: 'auto', alignSelf: 'flex-start', fontSize: '0.8125rem', color: 'var(--oc-accent)', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit', textDecoration: 'underline', textUnderlineOffset: '2px' }}>
                        Configure →
                      </button>
                    )}
                  </div>
                )
              })}
        </div>
      </section>

      {/* ── Add Companies ─────────────────────────────────────── */}
      <section>
        <p className="oc-section-heading">Add Companies</p>
        <form onSubmit={onUpload} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={isDragActive ? 'oc-upload-zone oc-upload-zone-active' : 'oc-upload-zone'}
          >
            <IconUpload size={28} className="oc-icon-muted" />
            <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', margin: 0, textAlign: 'center' }}>
              {file ? (
                <><strong style={{ color: 'var(--oc-text)', fontWeight: 600 }}>{file.name}</strong> ready to upload</>
              ) : (
                'Drop a CSV, TXT, XLS, or XLSX file here'
              )}
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

      {/* ── Recent activity ───────────────────────────────────── */}
      {(recentScrapeJobs.length > 0 || recentRuns.length > 0) && (
        <section>
          <p className="oc-section-heading">Recent Activity</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
            {recentScrapeJobs.slice(0, 3).map((job) => (
              <div key={job.id} className="oc-activity-row">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 700, color: 'var(--s1)', flexShrink: 0, minWidth: '1.75rem' }}>S1</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--oc-text)', fontSize: '0.9375rem' }}>{job.domain}</span>
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', flexShrink: 0 }}>{job.state}</span>
              </div>
            ))}
            {recentRuns.slice(0, 3).map((run) => (
              <div key={run.id} className="oc-activity-row">
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 700, color: 'var(--s2)', flexShrink: 0, minWidth: '1.75rem' }}>S2</span>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--oc-text)', fontSize: '0.9375rem' }}>{run.prompt_name ?? 'Run'}</span>
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', flexShrink: 0 }}>{run.status}</span>
              </div>
            ))}
          </div>
        </section>
      )}

    </div>
  )
}
