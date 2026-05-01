import { useEffect, useReducer, useRef, useState } from 'react'
import type {
  CompanyList,
  CompanyListItem,
  ContactCompanyListResponse,
  ContactCompanySummary,
  DiscoveredContactCountsResponse,
  DecisionFilter,
  StatsResponse,
} from '../../../lib/types'
import { listDiscoveredCompanies } from '../../../lib/api'
import { parseApiError } from '../../../lib/utils'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { decisionBgClass } from '../../ui/badgeUtils'
import { SortableHeader } from '../../ui/SortableHeader'
import { Pager } from '../../ui/Pager'
import { PipelineStageCompanyTableRow } from './PipelineStageCompanyTableRow'

type AuditMode = 'off' | 'no_matches' | 'matched'

const AUDIT_PAGE_SIZE = 50

type AuditState = {
  data: ContactCompanyListResponse | null
  isLoading: boolean
  error: string
}

type AuditAction =
  | { type: 'loading' }
  | { type: 'success'; data: ContactCompanyListResponse }
  | { type: 'error'; error: string }
  | { type: 'settled' }

function auditReducer(state: AuditState, action: AuditAction): AuditState {
  if (action.type === 'loading') return { ...state, isLoading: true, error: '' }
  if (action.type === 'success') return { ...state, data: action.data }
  if (action.type === 'error') return { ...state, error: action.error }
  return { ...state, isLoading: false }
}

/** Build the minimal `CompanyListItem` shape the contacts drawer needs. */
function summaryToCompanyStub(summary: ContactCompanySummary): CompanyListItem {
  return {
    id: summary.company_id,
    upload_id: '',
    upload_filename: '',
    raw_url: `https://${summary.domain}`,
    normalized_url: `https://${summary.domain}`,
    domain: summary.domain,
    pipeline_stage: 'contact_ready',
    created_at: '',
    last_activity: '',
    latest_decision: null,
    latest_confidence: null,
    latest_scrape_job_id: null,
    latest_scrape_status: null,
    latest_scrape_terminal: null,
    latest_analysis_pipeline_run_id: null,
    latest_analysis_job_id: null,
    latest_analysis_status: null,
    latest_analysis_terminal: null,
    feedback_thumbs: null,
    feedback_comment: null,
    feedback_manual_label: null,
    latest_scrape_error_code: null,
    latest_scrape_failure_reason: null,
    contact_count: summary.email_count,
    discovered_contact_count: summary.total_count,
    discovered_title_matched_count: summary.title_matched_count,
    revealed_contact_count: summary.email_count,
    contact_fetch_status: null,
  }
}

interface S3ContactFetchViewProps {
  campaignId: string | null
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  decisionFilter: DecisionFilter
  selectedIds: string[]
  totalMatching: number | null
  search: string
  isLoading: boolean
  isFetching: boolean
  isSelectingAll: boolean
  discoveredCounts: DiscoveredContactCountsResponse | null
  stats: StatsResponse | null
  onDecisionFilterChange: (filter: DecisionFilter) => void
  onSearchChange: (value: string) => void
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onFetchOne: (company: CompanyListItem) => void
  onFetchSelected: () => void
  onResetStuck?: () => void
  onViewContacts: (company: CompanyListItem) => void
  offset: number
  pageSize: number
  onPagePrev: () => void
  onPageNext: () => void
  onPageSizeChange: (size: number) => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
}

const DECISION_FILTERS: Array<{ value: DecisionFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'labeled', label: 'Labeled' },
  { value: 'possible', label: 'Possible' },
  { value: 'unknown', label: 'Unknown' },
  { value: 'crap', label: 'Crap' },
  { value: 'unlabeled', label: 'Unlabeled' },
]


export function S3ContactFetchView({
  campaignId,
  companies,
  letterCounts,
  activeLetters,
  decisionFilter,
  selectedIds,
  totalMatching,
  search,
  isLoading,
  isFetching,
  isSelectingAll,
  discoveredCounts,
  stats,
  onDecisionFilterChange,
  onSearchChange,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onFetchOne,
  onFetchSelected,
  onResetStuck,
  onViewContacts,
  offset,
  pageSize,
  onPagePrev,
  onPageNext,
  onPageSizeChange,
  sortBy,
  sortDir,
  onSort,
}: S3ContactFetchViewProps) {
  const selectedSet = new Set(selectedIds)

  // ── Title-match audit: list companies with discovered contacts but 0/>0 title matches ──
  const [auditMode, setAuditMode] = useState<AuditMode>('off')
  const [auditSearch, setAuditSearch] = useState('')
  const [auditOffset, setAuditOffset] = useState(0)
  const [auditState, dispatchAudit] = useReducer(auditReducer, {
    data: null,
    isLoading: false,
    error: '',
  })
  const auditRequestRef = useRef(0)

  const setAuditSearchAndReset = (value: string) => {
    setAuditSearch(value)
    setAuditOffset(0)
  }

  const setAuditModeAndReset = (value: AuditMode) => {
    if (value !== 'off') setAuditSearch(search)
    setAuditMode(value)
    setAuditOffset(0)
  }

  useEffect(() => {
    if (!campaignId || auditMode === 'off') {
      auditRequestRef.current += 1
      return
    }
    const reqId = auditRequestRef.current + 1
    auditRequestRef.current = reqId
    dispatchAudit({ type: 'loading' })
    const gapOptions = auditMode === 'no_matches'
      ? { matchGapFilter: 'contacts_no_match' as const }
      : { titleMatch: true }
    const trimmed = auditSearch.trim()
    listDiscoveredCompanies({
      campaignId,
      ...gapOptions,
      limit: AUDIT_PAGE_SIZE,
      offset: auditOffset,
      ...(trimmed ? { search: trimmed } : {}),
    })
      .then((response) => {
        if (auditRequestRef.current !== reqId) return
        dispatchAudit({ type: 'success', data: response })
      })
      .catch((err) => {
        if (auditRequestRef.current !== reqId) return
        dispatchAudit({ type: 'error', error: parseApiError(err) })
      })
      .finally(() => {
        if (auditRequestRef.current === reqId) dispatchAudit({ type: 'settled' })
      })
  }, [auditMode, auditOffset, campaignId, auditSearch])

  const isAuditActive = auditMode !== 'off'
  const shouldShowAuditState = Boolean(campaignId && isAuditActive)
  const effectiveIsAuditLoading = shouldShowAuditState && auditState.isLoading
  const effectiveAuditError = shouldShowAuditState ? auditState.error : ''
  const auditItems: ContactCompanySummary[] = shouldShowAuditState ? auditState.data?.items ?? [] : []
  const auditTotal = shouldShowAuditState ? auditState.data?.total ?? null : null
  const auditHasMore = shouldShowAuditState ? auditState.data?.has_more ?? false : false
  const controlsDisabled = isLoading || effectiveIsAuditLoading

  const visibleCompanies = companies?.items ?? []

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  const displayCount = companies?.total ?? 0
  const effectiveTotalMatching = totalMatching ?? companies?.total ?? null
  const contactFetch = stats?.contact_fetch
  const cfRunning = contactFetch?.running ?? 0
  const cfQueued = contactFetch?.queued ?? 0
  const cfCompleted = contactFetch?.succeeded ?? 0
  const cfFailed = contactFetch?.failed ?? 0
  const cfTotal = contactFetch?.total ?? 0
  const cfPct = contactFetch?.pct_done ?? 0
  const cfProcessed = cfCompleted + cfFailed
  const cfHasActivity = cfRunning > 0 || cfQueued > 0

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 space-y-2 pb-1" style={{ backgroundColor: 'var(--oc-bg)' }}>
      {/* Header */}
      <div className="rounded-xl px-3 py-2.5" style={{ borderLeft: '3px solid var(--s3)', backgroundColor: 'var(--s3-bg)' }}>
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <h2 className="text-base font-bold" style={{ color: 'var(--s3-text)' }}>S3 · Contact Discovery</h2>
            <p className="text-xs" style={{ color: 'var(--s3-text)', opacity: 0.7 }}>
              Discover possible contacts without revealing emails · {companies != null ? `${displayCount.toLocaleString()} companies` : '—'}
            </p>
          </div>
        {/* Search */}
        <div className="relative">
          <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            value={isAuditActive ? auditSearch : search}
            onChange={(e) => {
              const next = e.target.value
              if (isAuditActive) setAuditSearchAndReset(next)
              else onSearchChange(next)
            }}
            disabled={controlsDisabled}
            placeholder="Search domains…"
            className="rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--s3) focus:bg-white disabled:cursor-not-allowed disabled:opacity-60"
            style={{ width: 180 }}
          />
        </div>
        </div>
        {contactFetch && (cfHasActivity || cfCompleted > 0 || cfFailed > 0) && (
          <div className="mt-2 flex items-center gap-3 border-t border-(--oc-border) pt-1.5 text-xs text-(--oc-muted)">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${cfHasActivity ? 'animate-pulse bg-amber-400' : 'bg-(--oc-border)'}`} />
            <span className="flex items-center gap-1">
              {cfRunning > 0 && <span className="text-amber-600"><strong>{cfRunning.toLocaleString()}</strong> running ·</span>}
              {cfQueued > 0 && <span><strong>{cfQueued.toLocaleString()}</strong> queued ·</span>}
              {cfCompleted > 0 && <span className="text-emerald-600"><strong>{cfCompleted.toLocaleString()}</strong> done</span>}
              {cfFailed > 0 && <span className="text-red-500"> · <strong>{cfFailed.toLocaleString()}</strong> failed</span>}
            </span>
            <div className="flex-1 h-1 overflow-hidden rounded-full bg-(--oc-border)">
              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(cfPct, 100)}%`, backgroundColor: 'var(--s3)' }} />
            </div>
            <span className="tabular-nums shrink-0">{cfProcessed.toLocaleString()} / {cfTotal.toLocaleString()}</span>
            {cfRunning > 0 && onResetStuck && (
              <button
                type="button"
                onClick={onResetStuck}
                className="shrink-0 rounded px-2 py-0.5 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-300 transition hover:bg-amber-50"
              >
                Reset stuck
              </button>
            )}
          </div>
        )}
      </div>

      {/* Contact stats bar */}
      {discoveredCounts && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Discovered', value: discoveredCounts.total, color: '#14532d', bg: '#dcfce7' },
            { label: 'Title matched', value: discoveredCounts.matched, color: '#0f766e', bg: '#ccfbf1' },
            { label: 'Fresh', value: discoveredCounts.fresh, color: '#0369a1', bg: '#dbeafe' },
            { label: 'Stale', value: discoveredCounts.stale, color: '#92400e', bg: '#fef3c7' },
          ].map(({ label, value, color, bg }) => (
            <div
              key={label}
              className="rounded-xl border px-3 py-1.5 text-xs"
              style={{ borderColor: color + '33', backgroundColor: bg }}
            >
              <span className="font-black tabular-nums" style={{ color }}>{value.toLocaleString()}</span>
              <span className="ml-1.5" style={{ color: color + 'bb' }}>{label}</span>
            </div>
          ))}
        </div>
      )}

      {!isAuditActive && (
        <LetterStrip
          multiSelect
          activeLetters={activeLetters}
          counts={letterCounts}
          onToggle={onToggleLetter}
          onClear={onClearLetters}
          disabled={controlsDisabled}
        />
      )}

      {/* Title-match audit chips — lets ops verify whether title rules catch the intended contacts */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-(--oc-muted)">Title-match audit</span>
          {([
          { value: 'off', label: 'Off' },
          { value: 'no_matches', label: 'Discovered · 0 matches' },
          { value: 'matched', label: 'Discovered · has matches' },
        ] as const).map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => setAuditModeAndReset(value)}
            disabled={controlsDisabled}
            className="rounded-full border px-3 py-1 text-xs font-medium transition"
            style={
              auditMode === value
                ? { borderColor: 'var(--s3)', backgroundColor: 'var(--s3-bg)', color: 'var(--s3-text)', fontWeight: 700 }
                : controlsDisabled
                  ? { borderColor: 'var(--oc-border)', color: 'var(--oc-border)' }
                  : { borderColor: 'var(--oc-border)', color: 'var(--oc-muted)' }
            }
          >
            {label}
          </button>
        ))}
        {isAuditActive && (
          <span className="ml-1 text-[11px] text-(--oc-muted)">
            {auditMode === 'no_matches'
              ? 'Companies whose discovered contacts contain zero title matches — audit the match criteria.'
              : 'Companies with at least one title-matched contact.'}
          </span>
        )}
      </div>

      {!isAuditActive && (
        <>
          {/* Decision filter pills + pager */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1.5">
              {DECISION_FILTERS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onDecisionFilterChange(value)}
                  disabled={controlsDisabled}
                  className="rounded-full border px-3 py-1 text-xs font-medium transition"
                  style={
                    decisionFilter === value
                      ? { borderColor: 'var(--s3)', backgroundColor: 'var(--s3-bg)', color: 'var(--s3-text)', fontWeight: 700 }
                      : controlsDisabled
                        ? { borderColor: 'var(--oc-border)', color: 'var(--oc-border)' }
                        : { borderColor: 'var(--oc-border)', color: 'var(--oc-muted)' }
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <Pager offset={offset} pageSize={pageSize} total={companies?.total ?? null} hasMore={companies?.has_more ?? false} onPrev={onPagePrev} onNext={onPageNext} onPageSizeChange={onPageSizeChange} disabled={controlsDisabled} />
          </div>

          <SelectionBar
            stageColor="--s3"
            stageBg="--s3-bg"
            selectedCount={selectedIds.length}
            totalMatching={effectiveTotalMatching}
            activeLetters={activeLetters}
            onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
            isSelectingAll={isSelectingAll}
            onClear={onClearSelection}
            disabled={controlsDisabled}
          >
            <button
              type="button"
              onClick={() => onFetchSelected()}
              disabled={controlsDisabled || isFetching || selectedIds.length === 0}
              className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
              style={{ backgroundColor: 'var(--s3)' }}
            >
              {isFetching ? '…' : 'Discover Contacts'}
            </button>
          </SelectionBar>
        </>
      )}

      {isAuditActive && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-(--oc-muted)">
            {auditTotal != null
              ? `${auditTotal.toLocaleString()} compan${auditTotal === 1 ? 'y' : 'ies'} match this audit filter.`
              : '—'}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={auditOffset === 0 || controlsDisabled}
              onClick={() => setAuditOffset(Math.max(0, auditOffset - AUDIT_PAGE_SIZE))}
              className="flex h-6 w-6 items-center justify-center rounded-md border border-(--oc-border) bg-(--oc-surface-strong) text-xs transition hover:bg-(--oc-surface) disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Previous page"
            >
              ‹
            </button>
            <span className="min-w-[90px] text-center text-[11px] font-medium text-(--oc-muted)">
              {auditTotal != null
                ? `${(auditOffset + 1).toLocaleString()}–${Math.min(auditOffset + AUDIT_PAGE_SIZE, auditTotal).toLocaleString()} of ${auditTotal.toLocaleString()}`
                : `${(auditOffset + 1).toLocaleString()}–${(auditOffset + AUDIT_PAGE_SIZE).toLocaleString()}`}
            </span>
            <button
              type="button"
              disabled={!auditHasMore || controlsDisabled}
              onClick={() => setAuditOffset(auditOffset + AUDIT_PAGE_SIZE)}
              className="flex h-6 w-6 items-center justify-center rounded-md border border-(--oc-border) bg-(--oc-surface-strong) text-xs transition hover:bg-(--oc-surface) disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Next page"
            >
              ›
            </button>
          </div>
        </div>
      )}
      </div>{/* ── /sticky controls ── */}

      {isAuditActive ? (
        <div className="oc-panel overflow-hidden">
          {effectiveAuditError && (
            <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{effectiveAuditError}</div>
          )}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-(--oc-border) text-xs text-(--oc-muted)">
                <th className="p-3 text-left font-semibold">Domain</th>
                <th className="p-3 text-right font-semibold">Discovered</th>
                <th className="p-3 text-right font-semibold">Title matched</th>
                <th className="p-3 text-right font-semibold">With email</th>
                <th className="p-3 text-right font-semibold">Last discovered</th>
                <th className="p-3 text-left font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {effectiveIsAuditLoading && Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-(--oc-border)">
                  <td className="p-3"><div className="oc-skeleton h-4 w-36 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-8 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-8 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-8 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-20 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-6 w-16 rounded-lg" /></td>
                </tr>
              ))}
              {!effectiveIsAuditLoading && auditItems.length === 0 && !effectiveAuditError && (
                <tr>
                  <td colSpan={6} className="px-6 py-10 text-center">
                    <p className="text-sm font-semibold text-(--oc-text)">
                      {auditMode === 'no_matches'
                        ? 'No companies with discovered contacts and zero title matches.'
                        : 'No companies have title-matched contacts yet.'}
                    </p>
                    <p className="mt-1 text-xs text-(--oc-muted)">
                      {auditMode === 'no_matches'
                        ? 'Either the match criteria are catching everything or contacts have not been discovered.'
                        : 'Try discovering contacts for more companies or broadening your title rules.'}
                    </p>
                  </td>
                </tr>
              )}
              {!effectiveIsAuditLoading && auditItems.map((summary) => {
                const matchRate = summary.total_count > 0
                  ? Math.round((summary.title_matched_count / summary.total_count) * 100)
                  : 0
                return (
                  <tr key={summary.company_id} className="border-b border-(--oc-border) last:border-0">
                    <td className="p-3">
                      <a
                        href={`https://${summary.domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-[12px] font-medium hover:underline"
                        style={{ color: 'var(--s3)' }}
                      >
                        {summary.domain}
                      </a>
                    </td>
                    <td className="p-3 text-right font-mono text-xs">{summary.total_count.toLocaleString()}</td>
                    <td className="p-3 text-right">
                      <span
                        className="font-mono text-xs font-semibold"
                        style={{ color: summary.title_matched_count === 0 ? '#b91c1c' : '#15803d' }}
                      >
                        {summary.title_matched_count.toLocaleString()}
                        {summary.total_count > 0 && (
                          <span className="ml-1 text-[10px] font-normal text-(--oc-muted)">({matchRate}%)</span>
                        )}
                      </span>
                    </td>
                    <td className="p-3 text-right font-mono text-xs">{summary.email_count.toLocaleString()}</td>
                    <td className="p-3 text-right text-[11px] text-(--oc-muted)">
                      {summary.last_contact_attempted_at
                        ? new Date(summary.last_contact_attempted_at).toLocaleDateString()
                        : '—'}
                    </td>
                    <td className="p-3">
                      <button
                        type="button"
                        onClick={() => onViewContacts(summaryToCompanyStub(summary))}
                        disabled={controlsDisabled}
                        className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s3) hover:text-(--s3-text)"
                      >
                        View emails
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
      <div className="oc-panel overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-(--oc-border) text-xs text-(--oc-muted)">
              <th className="w-8 p-3">
                <input
                  type="checkbox"
                  disabled={controlsDisabled}
                  checked={allVisibleSelected}
                  ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                  onChange={() => onToggleAll(allVisibleSelected ? [] : visibleCompanies.map((c) => c.id))}
                  className="cursor-pointer disabled:cursor-not-allowed"
                />
              </th>
              <SortableHeader label="Domain" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
              <SortableHeader label="Activity" field="last_activity" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
              <SortableHeader label="Decision" field="decision" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
              <SortableHeader label="Discovered" field="discovered_contact_count" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
              <th className="p-3 text-left font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 8 }).map((_, i) => (
              <tr key={i} className="border-b border-(--oc-border)">
                <td className="p-3"><div className="oc-skeleton h-4 w-4 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-36 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-14 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-5 w-16 rounded-full" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-8 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-6 w-20 rounded-lg" /></td>
              </tr>
            ))}
            {!isLoading && visibleCompanies.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-10 text-center">
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-(--oc-text)">
                      {decisionFilter === 'all'
                        ? 'No companies yet'
                        : `No companies match "${decisionFilter}"`}
                    </p>
                    <p className="text-xs text-(--oc-muted)">
                      {decisionFilter === 'all'
                        ? 'Upload companies first or broaden the current filters.'
                        : 'Try another decision filter or clear the current search.'}
                    </p>
                  </div>
                </td>
              </tr>
            )}
            {visibleCompanies.map((c) => (
              <PipelineStageCompanyTableRow
                key={c.id}
                company={c}
                selected={selectedSet.has(c.id)}
                checkboxDisabled={controlsDisabled}
                onToggle={() => onToggleRow(c.id)}
                stageAccentVar="--s3"
                stageBgVar="--s3-bg"
              >
                <td className="p-3">
                  {(c.feedback_manual_label ?? c.latest_decision) ? (
                    <Badge className={decisionBgClass(c.feedback_manual_label ?? c.latest_decision)}>
                      {c.feedback_manual_label ?? c.latest_decision}
                    </Badge>
                  ) : <span className="text-xs text-(--oc-muted)">—</span>}
                </td>
                <td className="p-3 text-xs">
                  <div className="font-mono font-semibold">{(c.discovered_contact_count ?? 0).toLocaleString()}</div>
                  {(c.discovered_title_matched_count ?? 0) > 0 && (
                    <div className="text-[10px] text-(--oc-muted)">
                      {(c.discovered_title_matched_count ?? 0).toLocaleString()} matched
                    </div>
                  )}
                </td>
                <td className="p-3">
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      onClick={() => onViewContacts(c)}
                      disabled={controlsDisabled || (c.revealed_contact_count ?? c.contact_count ?? 0) === 0}
                      className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s3) hover:text-(--s3-text) disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Emails
                    </button>
                    <button
                      type="button"
                      onClick={() => onFetchOne(c)}
                      disabled={controlsDisabled}
                      className="rounded-lg px-2.5 py-1.5 text-[11px] font-bold text-white transition"
                      style={{ backgroundColor: 'var(--s3)' }}
                    >
                      Discover
                    </button>
                  </div>
                </td>
              </PipelineStageCompanyTableRow>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}
