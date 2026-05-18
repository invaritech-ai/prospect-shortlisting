import type { CompanyList, CompanyListItem, CostStatsResponse, PipelineCostSummaryRead, PipelineRunProgressRead } from '../../../lib/types'
import { companyListBrowseUrl, type FullPipelineStatusFilter } from '../../../lib/fullPipelineFilters'
import { getResumeStageForCompany } from '../../../lib/pipelineMappings'
import { MOCK_FULL_PIPELINE_COMPANIES } from '../../../lib/useAppData'
import { LetterStrip }      from '../../ui/LetterStrip'
import { Pager }            from '../../ui/Pager'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'
import { SelectionBar }     from '../../ui/SelectionBar'

// ── Stage status helpers ──────────────────────────────────────────────────────

type StatusVariant = 'ok' | 'run' | 'warn' | 'err' | 'neu'

interface CellStatus { label: string; variant: StatusVariant }

const VAR: Record<StatusVariant, { color: string; bg: string }> = {
  ok:   { color: 'var(--oc-success-text)', bg: 'var(--oc-success-bg)' },
  run:  { color: 'var(--oc-warn-text)',    bg: 'var(--oc-warn-bg)' },
  warn: { color: 'var(--s3-text)',         bg: 'var(--s3-bg)' },
  err:  { color: 'var(--oc-fail-text)',    bg: 'var(--oc-fail-bg)' },
  neu:  { color: 'var(--oc-muted)',        bg: 'var(--oc-surface-dim)' },
}

function StatusBadge({ label, variant }: CellStatus) {
  if (label === '—') return <span style={{ fontSize: '0.75rem', color: 'var(--oc-border)' }}>—</span>
  const { color, bg } = VAR[variant]
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
      padding: '0.1875rem 0.5625rem', borderRadius: '9999px',
      fontSize: '0.6875rem', fontWeight: 700,
      color, backgroundColor: bg, whiteSpace: 'nowrap',
    }}>
      <span style={{
        width: '5px', height: '5px', borderRadius: '9999px',
        backgroundColor: color, flexShrink: 0,
        animation: variant === 'run' ? 'oc-ping 1.5s cubic-bezier(0,0,0.2,1) infinite' : undefined,
      }} />
      {label}
    </span>
  )
}

function s1Status(c: CompanyListItem): CellStatus {
  const s = c.latest_scrape_status?.toLowerCase()
  if (!s)                        return { label: '—',         variant: 'neu' }
  if (s === 'completed')         return { label: 'Done',       variant: 'ok'  }
  if (s === 'created')           return { label: 'Queued',     variant: 'run' }
  if (s === 'running')           return { label: 'Scraping…',  variant: 'run' }
  if (s === 'cancelled')         return { label: 'Cancelled',  variant: 'neu' }
  if (s === 'site_unavailable')  return { label: 'Site down',  variant: 'err' }
  if (s === 'failed' || s === 'step1_failed') return { label: 'Failed', variant: 'err' }
  return { label: s, variant: 'neu' }
}

function s2Status(c: CompanyListItem): CellStatus {
  const label = (c.feedback_manual_label ?? c.latest_decision ?? '').toLowerCase()
  if (label === 'possible') return { label: 'Possible', variant: 'ok'  }
  if (label === 'crap')     return { label: 'Rejected',  variant: 'err' }
  if (label === 'unknown')  return { label: 'Unknown',   variant: 'neu' }
  const as = c.latest_analysis_status?.toLowerCase()
  if (as === 'running' || as === 'queued') return { label: 'Analysing…', variant: 'run' }
  if (as === 'dead')   return { label: 'Stuck',  variant: 'warn' }
  if (as === 'failed') return { label: 'Failed', variant: 'err'  }
  return { label: 'Waiting', variant: 'neu' }
}

function s3Status(c: CompanyListItem): CellStatus {
  const total = (c.discovered_contact_count ?? 0) + (c.revealed_contact_count ?? 0)
  if (total > 0) return { label: `${total} found`, variant: 'ok' }
  const cs = c.contact_fetch_status?.toLowerCase()
  if (cs === 'running' || cs === 'queued') return { label: 'Fetching…', variant: 'run'  }
  if (cs === 'succeeded')                  return { label: 'None',      variant: 'neu'  }
  if (cs === 'failed')                     return { label: 'Failed',    variant: 'err'  }
  return { label: '—', variant: 'neu' }
}

function s5Status(c: CompanyListItem): CellStatus {
  const emails = c.contact_count ?? 0
  if (emails > 0) return { label: `${emails} email${emails > 1 ? 's' : ''}`, variant: 'ok' }
  if ((c.discovered_contact_count ?? 0) > 0) return { label: 'Pending', variant: 'neu' }
  return { label: '—', variant: 'neu' }
}

// ── Stage column definitions ──────────────────────────────────────────────────

const STAGES = [
  { key: 's1', label: 'Scraping',  color: 'var(--s1)', bg: 'var(--s1-bg)', text: 'var(--s1-text)', fn: s1Status },
  { key: 's2', label: 'AI Review', color: 'var(--s2)', bg: 'var(--s2-bg)', text: 'var(--s2-text)', fn: s2Status },
  { key: 's3', label: 'Contacts',  color: 'var(--s3)', bg: 'var(--s3-bg)', text: 'var(--s3-text)', fn: s3Status },
  { key: 's5', label: 'Validation',color: 'var(--s5)', bg: 'var(--s5-bg)', text: 'var(--s5-text)', fn: s5Status },
] as const

const STATUS_FILTERS: Array<{ value: FullPipelineStatusFilter; label: string }> = [
  { value: 'all',               label: 'All'           },
  { value: 'not-started',       label: 'Not started'   },
  { value: 'in-progress',       label: 'In progress'   },
  { value: 'complete',          label: 'Complete'      },
  { value: 'permanent-failures',label: 'Permanent fail'},
  { value: 'soft-failures',     label: 'Soft fail'     },
]

// ── Props ─────────────────────────────────────────────────────────────────────

interface FullPipelineViewProps {
  activeCampaignName: string | null
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetter: string | null
  selectedIds: string[]
  resumeActionState: Record<string, string>
  isLoading: boolean
  offset: number
  pageSize: number
  statusFilter: FullPipelineStatusFilter
  search: string
  onLetterChange: (l: string | null) => void
  onStatusFilterChange: (filter: FullPipelineStatusFilter) => void
  onSearchChange: (value: string) => void
  onToggleRow: (id: string) => void
  onToggleAll: (ids: string[]) => void
  onClearSelection: () => void
  onScrapeSelected: () => void
  onStartCampaignPipeline: () => void
  onResumeCompany: (company: CompanyListItem) => void
  isScraping: boolean
  isStartingCampaignPipeline: boolean
  onPagePrev: () => void
  onPageNext: () => void
  onPageSizeChange: (size: number) => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
  isSelectingAllMatching: boolean
  onSelectAllMatching: () => void
  latestRunProgress: PipelineRunProgressRead | null
  campaignCostSummary: PipelineCostSummaryRead | null
  campaignCostBreakdown: CostStatsResponse | null
  mockFallback?: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────

export function FullPipelineView({
  activeCampaignName, companies, letterCounts, activeLetter,
  selectedIds, resumeActionState, isLoading, offset, pageSize,
  statusFilter, search,
  onLetterChange, onStatusFilterChange, onSearchChange,
  onToggleRow, onToggleAll, onClearSelection,
  onScrapeSelected, onStartCampaignPipeline, onResumeCompany,
  isScraping, isStartingCampaignPipeline,
  onPagePrev, onPageNext, onPageSizeChange, onSort, sortBy, sortDir,
  isSelectingAllMatching, onSelectAllMatching,
  latestRunProgress, campaignCostSummary,
  mockFallback,
}: FullPipelineViewProps) {
  const selectedSet = new Set(selectedIds)

  // Use mock data when backend hasn't loaded anything yet
  const mockList: CompanyList = { items: MOCK_FULL_PIPELINE_COMPANIES, total: MOCK_FULL_PIPELINE_COMPANIES.length, has_more: false, limit: 50, offset: 0 }
  const effectiveCompanies  = (companies ?? (mockFallback ? mockList : null))
  const effectiveIsLoading  = !mockFallback && isLoading
  const visibleCompanies    = effectiveCompanies?.items ?? []
  const allSelected      = visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someSelected     = !allSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, minHeight: 0, flex: 1, overflow: 'hidden' }}>

      {/* ── Sticky top bar ──────────────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 20, flexShrink: 0,
        display: 'flex', flexDirection: 'column', gap: '0.625rem',
        borderBottom: '1px solid var(--oc-border)',
        background: 'color-mix(in srgb, var(--oc-bg) 97%, transparent)',
        backdropFilter: 'blur(8px)',
        padding: '0.75rem 0 0.75rem',
      }}>

        {/* Row 1: identity + search + primary action */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {/* Identity */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
            <span style={{ width: '7px', height: '7px', borderRadius: '2px', backgroundColor: 'var(--oc-accent)' }} />
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.375rem', color: 'var(--oc-accent)', margin: 0, lineHeight: 1 }}>
              Full Pipeline
            </h1>
          </div>
          {activeCampaignName && (
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', fontWeight: 500 }}>
              · {activeCampaignName}
            </span>
          )}
          {effectiveCompanies?.total != null && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
              {effectiveCompanies!.total.toLocaleString()} companies
            </span>
          )}
          {campaignCostSummary && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 600,
              padding: '0.1875rem 0.5625rem', borderRadius: '9999px',
              border: '1px solid var(--oc-border)', color: 'var(--oc-muted)',
            }}>
              ${Number(campaignCostSummary.total_cost_usd || 0).toFixed(4)} spend
            </span>
          )}

          <div style={{ flex: 1 }} />

          {/* Search */}
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <svg style={{ position: 'absolute', left: '0.625rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--oc-muted)', pointerEvents: 'none' }}
              width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              type="search" value={search} disabled={effectiveIsLoading}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search domains…"
              style={{
                paddingLeft: '1.875rem', paddingRight: '0.75rem',
                height: '34px', width: '200px',
                borderRadius: '9999px',
                border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                fontSize: '0.8125rem', fontFamily: 'inherit', color: 'var(--oc-text)',
                outline: 'none', transition: 'border-color 140ms',
              }}
              onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--oc-accent)' }}
              onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)' }}
            />
          </div>

          <button
            type="button"
            onClick={onStartCampaignPipeline}
            disabled={effectiveIsLoading || isStartingCampaignPipeline}
            style={{
              display: 'inline-flex', alignItems: 'center',
              height: '34px', padding: '0 1rem', borderRadius: '0.5rem',
              border: 'none', background: 'var(--oc-accent)', color: '#fff',
              fontWeight: 700, fontSize: '0.8125rem', fontFamily: 'inherit',
              cursor: isStartingCampaignPipeline ? 'not-allowed' : 'pointer',
              opacity: (effectiveIsLoading || isStartingCampaignPipeline) ? 0.55 : 1,
              whiteSpace: 'nowrap', flexShrink: 0,
              boxShadow: '0 2px 6px color-mix(in srgb, var(--oc-accent) 30%, transparent)',
            }}
          >
            {isStartingCampaignPipeline ? 'Starting…' : 'Run full pipeline'}
          </button>
        </div>

        {/* Row 2: status filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: '0.3125rem', flexWrap: 'wrap' }}>
            {STATUS_FILTERS.map((f) => {
              const active = statusFilter === f.value
              return (
                <button
                  key={f.value}
                  type="button"
                  onClick={() => onStatusFilterChange(f.value)}
                  disabled={effectiveIsLoading}
                  style={{
                    padding: '0.3125rem 0.75rem', borderRadius: '9999px',
                    border: `1.5px solid ${active ? 'var(--oc-accent)' : 'var(--oc-border)'}`,
                    background: active ? 'var(--oc-accent-soft)' : 'var(--oc-surface)',
                    color: active ? 'var(--oc-accent-ink)' : 'var(--oc-muted)',
                    fontWeight: active ? 700 : 500, fontSize: '0.75rem',
                    cursor: isLoading ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
                    opacity: isLoading ? 0.5 : 1, transition: 'all 140ms',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {f.label}
                </button>
              )
            })}
          </div>

          <span style={{ width: '1px', height: '18px', background: 'var(--oc-border)', flexShrink: 0 }} />

          <Pager
            offset={offset} pageSize={pageSize}
            total={effectiveCompanies?.total ?? null} hasMore={effectiveCompanies?.has_more ?? false}
            onPrev={onPagePrev} onNext={onPageNext}
            onPageSizeChange={onPageSizeChange} disabled={effectiveIsLoading}
          />

          <button
            type="button"
            disabled={effectiveIsLoading || isSelectingAllMatching}
            onClick={onSelectAllMatching}
            style={{
              padding: '0.3125rem 0.75rem', borderRadius: '9999px',
              border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
              color: 'var(--oc-accent-ink)', fontWeight: 600, fontSize: '0.75rem',
              cursor: 'pointer', fontFamily: 'inherit',
              opacity: (effectiveIsLoading || isSelectingAllMatching) ? 0.5 : 1,
              transition: 'all 140ms', whiteSpace: 'nowrap',
            }}
          >
            {isSelectingAllMatching ? 'Selecting…' : 'Select all matching'}
          </button>
        </div>

        {/* Row 3: letter strip */}
        <LetterStrip active={activeLetter} onChange={onLetterChange} counts={letterCounts} disabled={effectiveIsLoading} />

        {/* Live run progress */}
        {latestRunProgress && (
          <div style={{
            borderRadius: '0.625rem', border: '1px solid var(--oc-border)',
            background: 'var(--oc-surface)', padding: '0.625rem 0.875rem',
            display: 'flex', flexDirection: 'column', gap: '0.5rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--oc-text)' }}>
                Live run · {latestRunProgress.state}
              </span>
              <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>
                queued {latestRunProgress.queued_count} · reused {latestRunProgress.reused_count} · failed {latestRunProgress.failed_count}
              </span>
            </div>
            {Object.entries(latestRunProgress.stages).map(([stage, counts]) => {
              const total = Math.max(1, counts.total)
              const pct   = Math.min(100, Math.round(((counts.succeeded + counts.failed) / total) * 100))
              return (
                <div key={stage}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.625rem', color: 'var(--oc-muted)', marginBottom: '0.25rem' }}>
                    <span style={{ fontWeight: 600 }}>{stage}</span>
                    <span>{counts.running} running · {counts.succeeded} done · {counts.failed} failed</span>
                  </div>
                  <div style={{ height: '4px', borderRadius: '9999px', background: 'var(--oc-border)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: '9999px', width: `${pct}%`, background: 'var(--oc-accent)', transition: 'width 400ms ease' }} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Selection bar */}
      <SelectionBar
        stageColor="--oc-accent" stageBg="--oc-accent-soft"
        selectedCount={selectedIds.length} totalMatching={effectiveCompanies?.total ?? null}
        activeLetters={activeLetter ? new Set([activeLetter]) : new Set()}
        onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
        isSelectingAll={isSelectingAllMatching}
        onClear={onClearSelection} disabled={effectiveIsLoading}
      >
        <button
          type="button"
          onClick={onScrapeSelected}
          disabled={effectiveIsLoading || isScraping || selectedIds.length === 0}
          style={{
            padding: '0.375rem 0.875rem', borderRadius: '0.5rem',
            border: 'none', background: 'var(--oc-accent)', color: '#fff',
            fontWeight: 700, fontSize: '0.75rem', fontFamily: 'inherit',
            cursor: 'pointer', opacity: (effectiveIsLoading || isScraping || selectedIds.length === 0) ? 0.5 : 1,
          }}
        >
          {isScraping ? 'Starting…' : 'Start pipeline'}
        </button>
      </SelectionBar>

      {/* ── Table ──────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div style={{ minWidth: '760px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 10 }}>
              <tr style={{ borderBottom: '1px solid var(--oc-border)', background: 'color-mix(in srgb, var(--oc-surface) 97%, transparent)', backdropFilter: 'blur(4px)' }}>
                <th style={{ width: '2.5rem', padding: '0.625rem 0.75rem' }}>
                  <input
                    type="checkbox" disabled={effectiveIsLoading}
                    checked={allSelected}
                    ref={(el) => { if (el) el.indeterminate = someSelected }}
                    onChange={() => onToggleAll(allSelected ? [] : visibleCompanies.map((c) => c.id))}
                    style={{ cursor: 'pointer', accentColor: 'var(--oc-accent)' }}
                  />
                </th>
                <th style={{ padding: '0.625rem 0.75rem', textAlign: 'left', fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'var(--oc-muted)', minWidth: '200px' }}>
                  Domain
                </th>
                <th
                  onClick={() => !isLoading && onSort('last_activity')}
                  style={{ padding: '0.625rem 0.75rem', textAlign: 'left', fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'var(--oc-muted)', minWidth: '100px', cursor: isLoading ? 'not-allowed' : 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
                >
                  Last activity {sortBy === 'last_activity' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
                {STAGES.map((s) => (
                  <th key={s.key} style={{ padding: '0.625rem 0.75rem', textAlign: 'left', minWidth: '130px', background: `color-mix(in srgb, ${s.bg} 50%, transparent)` }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        width: '16px', height: '16px', borderRadius: '9999px', flexShrink: 0,
                        background: s.bg, color: s.text,
                        fontSize: '0.5625rem', fontWeight: 900,
                      }}>
                        {s.key === 's5' ? '4' : s.key[1]}
                      </span>
                      <span style={{ fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: s.text }}>
                        {s.label}
                      </span>
                    </div>
                  </th>
                ))}
                <th style={{ padding: '0.625rem 0.75rem', textAlign: 'left', fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.15em', color: 'var(--oc-muted)', minWidth: '100px' }}>
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {effectiveIsLoading && (
                <tr><td colSpan={8} style={{ padding: '3rem', textAlign: 'center', fontSize: '0.9375rem', color: 'var(--oc-muted)' }}>Loading…</td></tr>
              )}
              {!isLoading && visibleCompanies.length === 0 && (
                <tr><td colSpan={8} style={{ padding: '3rem', textAlign: 'center', fontSize: '0.9375rem', color: 'var(--oc-muted)' }}>No companies match this filter.</td></tr>
              )}
              {visibleCompanies.map((c) => {
                const isSelected  = selectedSet.has(c.id)
                const resumeStage = getResumeStageForCompany(c)
                const resumeLabel = resumeActionState[c.id]
                return (
                  <tr
                    key={c.id}
                    style={{
                      borderBottom: '1px solid var(--oc-border)',
                      background: isSelected ? 'color-mix(in srgb, var(--oc-accent-soft) 40%, transparent)' : undefined,
                      transition: 'background 120ms',
                    }}
                  >
                    <td style={{ padding: '0.625rem 0.75rem' }}>
                      <input type="checkbox" disabled={effectiveIsLoading} checked={isSelected}
                        onChange={() => onToggleRow(c.id)}
                        style={{ cursor: 'pointer', accentColor: 'var(--oc-accent)' }}
                      />
                    </td>
                    <td style={{ padding: '0.625rem 0.75rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                        <div style={{
                          width: '28px', height: '28px', borderRadius: '0.5rem', flexShrink: 0,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          border: '1px solid var(--oc-border)', background: 'var(--oc-surface)',
                          fontWeight: 800, fontSize: '0.6875rem', color: 'var(--oc-accent-ink)',
                        }}>
                          {c.domain[0].toUpperCase()}
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <a
                            href={companyListBrowseUrl(c)}
                            target="_blank" rel="noopener noreferrer"
                            style={{
                              display: 'block', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem',
                              fontWeight: 600, color: 'var(--oc-text)', textDecoration: 'none',
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--oc-accent)' }}
                            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-text)' }}
                          >
                            {c.domain}
                          </a>
                          <p style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', margin: 0 }}>
                            Added {new Date(c.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '0.625rem 0.75rem', fontSize: '0.75rem', color: 'var(--oc-muted)', fontVariantNumeric: 'tabular-nums' }}>
                      <RelativeTimeLabel timestamp={c.last_activity} prefix="" />
                    </td>
                    {STAGES.map((s) => (
                      <td key={s.key} style={{ padding: '0.625rem 0.75rem' }}>
                        <StatusBadge {...s.fn(c)} />
                      </td>
                    ))}
                    <td style={{ padding: '0.625rem 0.75rem' }}>
                      {resumeStage ? (
                        <button
                          type="button"
                          onClick={() => onResumeCompany(c)}
                          disabled={effectiveIsLoading || Boolean(resumeLabel)}
                          style={{
                            padding: '0.25rem 0.625rem', borderRadius: '0.375rem',
                            border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                            fontSize: '0.75rem', fontWeight: 600, color: 'var(--oc-muted)',
                            cursor: 'pointer', fontFamily: 'inherit', transition: 'all 140ms',
                            opacity: Boolean(resumeLabel) ? 0.5 : 1, whiteSpace: 'nowrap',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--oc-accent)'; e.currentTarget.style.color = 'var(--oc-accent-ink)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)'; e.currentTarget.style.color = 'var(--oc-muted)' }}
                        >
                          {resumeLabel ?? `Resume ${resumeStage}`}
                        </button>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: 'var(--oc-border)' }}>—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer pagination info */}
      {companies && (
        <div style={{
          flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderTop: '1px solid var(--oc-border)', padding: '0.5rem 0.75rem',
          fontSize: '0.75rem', color: 'var(--oc-muted)',
        }}>
          <span>{visibleCompanies.length.toLocaleString()} on this page</span>
          {companies.has_more && <span style={{ color: 'var(--oc-accent)' }}>Use letter filter or next page for more</span>}
        </div>
      )}
    </div>
  )
}
