import type { DragEvent, FormEvent } from 'react'
import type { CompanyCounts, StatsResponse, ScrapeJobRead, RunRead } from '../../../lib/types'
import { IconUpload } from '../../ui/icons'

function LiveDot({ color }: { color: string }) {
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ backgroundColor: color }} />
      <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
    </span>
  )
}

type PipelineStageView = 's1-scraping' | 's2-ai' | 's3-contacts' | 's4-reveal' | 's5-validation'

interface DashboardViewProps {
  companyCounts: CompanyCounts | null
  stats: StatsResponse | null
  recentScrapeJobs: ScrapeJobRead[]
  recentRuns: RunRead[]
  // Upload
  file: File | null
  isUploading: boolean
  isDragActive: boolean
  onSetFile: (f: File | null) => void
  onSetIsDragActive: (v: boolean) => void
  onUpload: (e: FormEvent) => void
  // Navigation
  hasSelectedCampaign: boolean
  onNavigate: (view: PipelineStageView) => void
  onOpenCampaigns: () => void
  onOpenOperations: () => void
}

interface StageCardDef {
  view: PipelineStageView
  label: string
  stageColor: string
  stageBg: string
  count: number | null
  hint: string
}

export function DashboardView({
  companyCounts,
  stats,
  recentScrapeJobs,
  recentRuns,
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
}: DashboardViewProps) {
  const cards: StageCardDef[] = [
    {
      view: 's1-scraping',
      label: 'S1 · Scraping',
      stageColor: '--s1',
      stageBg: '--s1-bg',
      count: companyCounts?.uploaded ?? null,
      hint: 'Companies not yet scraped',
    },
    {
      view: 's2-ai',
      label: 'S2 · AI Decision',
      stageColor: '--s2',
      stageBg: '--s2-bg',
      count: companyCounts?.scraped ?? null,
      hint: 'Scraped, awaiting classification',
    },
    {
      view: 's3-contacts',
      label: 'S3 · Contact Fetch',
      stageColor: '--s3',
      stageBg: '--s3-bg',
      count: companyCounts?.classified ?? null,
      hint: 'Classified, awaiting contacts',
    },
    {
      view: 's4-reveal',
      label: 'S4 · Reveal',
      stageColor: '--s4',
      stageBg: '--s4-bg',
      count: null,
      hint: 'Reveal contact emails',
    },
    {
      view: 's5-validation',
      label: 'S5 · Validation',
      stageColor: '--s5',
      stageBg: '--s5-bg',
      count: companyCounts?.contact_ready ?? null,
      hint: 'Contacts fetched, validate emails',
    },
  ]

  const handleDragOver = (e: DragEvent) => { e.preventDefault(); onSetIsDragActive(true) }
  const handleDragLeave = () => onSetIsDragActive(false)
  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    onSetIsDragActive(false)
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
        <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
          <p className="text-sm text-(--oc-muted)">
            Stage screens are campaign-scoped. Select a campaign first to run S1-S4 flows.
          </p>
          <button
            type="button"
            className="mt-3 rounded-xl bg-(--oc-accent) px-3 py-2 text-xs font-bold text-white"
            onClick={onOpenCampaigns}
          >
            Select campaign
          </button>
        </section>
      )}

      {/* Pipeline stage cards */}
      <section>
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wider text-(--oc-muted)">
          Pipeline
        </h2>
        <p className="mb-3 text-xs text-(--oc-muted)">
          Use stage cards for focused S1-S4 work. Use Full Pipeline for cross-stage triage and bulk actions.
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {cards.map((card) => {
            const isLive =
              (card.view === 's1-scraping' && (stats?.scrape?.running ?? 0) > 0) ||
              (card.view === 's2-ai' && (stats?.analysis?.running ?? 0) > 0) ||
              (card.view === 's3-contacts' && (stats?.contact_fetch?.running ?? 0) > 0) ||
              (card.view === 's5-validation' && (stats?.validation?.running ?? 0) > 0)
            return (
              <button
                key={card.view}
                type="button"
                onClick={() => {
                  if (!hasSelectedCampaign) {
                    onOpenCampaigns()
                    return
                  }
                  onNavigate(card.view)
                }}
                className="group flex flex-col gap-2 rounded-2xl border p-4 text-left transition hover:shadow-md"
                style={{
                  backgroundColor: `var(${card.stageBg})`,
                  borderColor: `var(${card.stageColor})`,
                }}
              >
                <span className="flex items-center gap-1.5">
                  <span
                    className="text-[10px] font-bold uppercase tracking-wider"
                    style={{ color: `var(${card.stageColor})` }}
                  >
                    {card.label}
                  </span>
                  {isLive && <LiveDot color={`var(${card.stageColor})`} />}
                </span>
                <span
                  className="text-3xl font-black tabular-nums"
                  style={{ color: `var(${card.stageColor})` }}
                >
                  {card.count != null ? card.count.toLocaleString() : '—'}
                </span>
                <span className="text-[11px] text-(--oc-muted)">
                  {card.hint}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* Stats row */}
      {hasQueueActivity && stats && (
        <div className="flex flex-wrap items-center gap-3">
          {(stats.scrape.running > 0 || stats.scrape.queued > 0 || stats.scrape.stuck_count > 0) && (
            <div className="flex items-center gap-2 rounded-xl border border-(--s1) bg-(--s1-bg) px-3 py-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ backgroundColor: 'var(--s1)' }} />
                <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--s1)' }} />
              </span>
              <span className="text-xs font-medium" style={{ color: 'var(--s1-text)' }}>
                {stats.scrape.running} running · {stats.scrape.queued} queued · {stats.scrape.stuck_count} stuck
              </span>
            </div>
          )}
          {(stats.analysis.running > 0 || stats.analysis.queued > 0 || stats.analysis.stuck_count > 0) && (
            <div className="flex items-center gap-2 rounded-xl border px-3 py-2" style={{ borderColor: 'var(--s2)', backgroundColor: 'var(--s2-bg)' }}>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ backgroundColor: 'var(--s2)' }} />
                <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--s2)' }} />
              </span>
              <span className="text-xs font-medium" style={{ color: 'var(--s2-text)' }}>
                {stats.analysis.running} running · {stats.analysis.queued} queued · {stats.analysis.stuck_count} stuck
              </span>
            </div>
          )}
          {stats.contact_fetch && (stats.contact_fetch.running > 0 || stats.contact_fetch.queued > 0 || stats.contact_fetch.stuck_count > 0) && (
            <div className="flex items-center gap-2 rounded-xl border px-3 py-2" style={{ borderColor: 'var(--s3)', backgroundColor: 'var(--s3-bg)' }}>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ backgroundColor: 'var(--s3)' }} />
                <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--s3)' }} />
              </span>
              <span className="text-xs font-medium" style={{ color: 'var(--s3-text)' }}>
                {stats.contact_fetch.running} running · {stats.contact_fetch.queued} queued · {stats.contact_fetch.stuck_count} stuck
              </span>
            </div>
          )}
          {stats.validation && (stats.validation.running > 0 || stats.validation.queued > 0 || stats.validation.stuck_count > 0) && (
            <div className="flex items-center gap-2 rounded-xl border px-3 py-2" style={{ borderColor: 'var(--s4)', backgroundColor: 'var(--s4-bg)' }}>
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75" style={{ backgroundColor: 'var(--s4)' }} />
                <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--s4)' }} />
              </span>
              <span className="text-xs font-medium" style={{ color: 'var(--s4-text)' }}>
                {stats.validation.running} running · {stats.validation.queued} queued · {stats.validation.stuck_count} stuck
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={onOpenOperations}
            className="rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-xs font-semibold text-(--oc-accent-ink) transition hover:border-(--oc-accent)"
          >
            View in Operations
          </button>
        </div>
      )}

      {/* Upload section */}
      <section>
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wider text-(--oc-muted)">
          Add Companies
        </h2>
        <form onSubmit={onUpload} className="flex flex-col gap-3">
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-8 transition ${
              isDragActive
                ? 'border-(--oc-accent) bg-(--oc-accent-soft)'
                : 'border-(--oc-border) bg-(--oc-surface) hover:border-(--oc-accent)/50'
            }`}
          >
            <IconUpload size={24} className="text-(--oc-muted)" />
            <p className="text-sm text-(--oc-muted)">
              {file ? file.name : 'Drop a CSV file here, or click to browse'}
            </p>
            <input
              type="file"
              accept=".csv"
              className="hidden"
              id="csv-upload"
              onChange={(e) => onSetFile(e.target.files?.[0] ?? null)}
            />
            <label
              htmlFor="csv-upload"
              className="cursor-pointer rounded-lg border border-(--oc-border) bg-white px-3 py-1.5 text-xs font-medium hover:border-(--oc-accent) hover:text-(--oc-accent) transition"
            >
              Choose file
            </label>
          </div>
          {file && (
            <button
              type="submit"
              disabled={isUploading}
              className="rounded-xl bg-(--oc-accent) px-4 py-2 text-sm font-bold text-white transition hover:opacity-90 disabled:opacity-60"
            >
              {isUploading ? 'Uploading…' : `Upload ${file.name}`}
            </button>
          )}
        </form>
      </section>

      {/* Recent activity */}
      {(recentScrapeJobs.length > 0 || recentRuns.length > 0) && (
        <section>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wider text-(--oc-muted)">
            Recent Activity
          </h2>
          <div className="space-y-1.5">
            {recentScrapeJobs.slice(0, 3).map((job) => (
              <div key={job.id} className="flex items-center gap-2 rounded-xl bg-(--oc-surface) px-3 py-2 text-xs">
                <span className="w-16 truncate font-bold" style={{ color: 'var(--s1)' }}>S1</span>
                <span className="flex-1 truncate text-(--oc-text)">{job.domain}</span>
                <span className="text-(--oc-muted)">{job.status}</span>
              </div>
            ))}
            {recentRuns.slice(0, 3).map((run) => (
              <div key={run.id} className="flex items-center gap-2 rounded-xl bg-(--oc-surface) px-3 py-2 text-xs">
                <span className="w-16 truncate font-bold" style={{ color: 'var(--s2)' }}>S2</span>
                <span className="flex-1 truncate text-(--oc-text)">{run.prompt_name ?? 'Run'}</span>
                <span className="text-(--oc-muted)">{run.status}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
