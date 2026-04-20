import { useEffect, useRef, useState } from 'react'
import type {
  CompanyList,
  CompanyListItem,
  ContactCompanyListResponse,
  ContactCompanySummary,
  ContactCountsResponse,
  DecisionFilter,
  StatsResponse,
} from '../../../lib/types'
import { listContactCompanies } from '../../../lib/api'
import { parseApiError } from '../../../lib/utils'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { decisionBgClass } from '../../ui/badgeUtils'
import { SortableHeader } from '../../ui/SortableHeader'
import { Pager } from '../../ui/Pager'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'

type AuditMode = 'off' | 'no_matches' | 'matched'

const AUDIT_PAGE_SIZE = 50

/** Build the minimal `CompanyListItem` shape the contacts drawer needs (id/domain/contact_count). */
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
    latest_decision: null,
    latest_confidence: null,
    latest_scrape_job_id: null,
    latest_scrape_status: null,
    latest_scrape_terminal: null,
    latest_analysis_run_id: null,
    latest_analysis_job_id: null,
    latest_analysis_status: null,
    latest_analysis_terminal: null,
    feedback_thumbs: null,
    feedback_comment: null,
    feedback_manual_label: null,
    latest_scrape_error_code: null,
    contact_count: summary.total_count,
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
  isLoading: boolean
  isFetching: boolean
  isSelectingAll: boolean
  contactCounts: ContactCountsResponse | null
  stats: StatsResponse | null
  onDecisionFilterChange: (filter: DecisionFilter) => void
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onFetchOne: (company: CompanyListItem, source: 'snov' | 'apollo' | 'both') => void
  onFetchSelected: (source: 'snov' | 'apollo' | 'both') => void
  onViewContacts: (company: CompanyListItem) => void
  onOpenTitleRules: () => void
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

const FETCH_BUTTONS: Array<{ source: 'apollo' | 'snov' | 'both'; label: string; bg: string }> = [
  { source: 'apollo', label: 'Fetch · Apollo', bg: '#15803d' },
  { source: 'snov', label: 'Fetch · Snov.io', bg: '#0369a1' },
  { source: 'both', label: 'Fetch · Both', bg: '#1e40af' },
]

export function S3ContactFetchView({
  campaignId,
  companies,
  letterCounts,
  activeLetters,
  decisionFilter,
  selectedIds,
  totalMatching,
  isLoading,
  isFetching,
  isSelectingAll,
  contactCounts,
  stats,
  onDecisionFilterChange,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onFetchOne,
  onFetchSelected,
  onViewContacts,
  onOpenTitleRules,
  offset,
  pageSize,
  onPagePrev,
  onPageNext,
  onPageSizeChange,
  sortBy,
  sortDir,
  onSort,
}: S3ContactFetchViewProps) {
  const [search, setSearch] = useState('')
  const selectedSet = new Set(selectedIds)

  // ── Title-match audit: list companies with contacts fetched but 0/>0 title matches ──
  const [auditMode, setAuditMode] = useState<AuditMode>('off')
  const [auditOffset, setAuditOffset] = useState(0)
  const [auditData, setAuditData] = useState<ContactCompanyListResponse | null>(null)
  const [isAuditLoading, setIsAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState('')
  const auditRequestRef = useRef(0)

  useEffect(() => {
    setAuditOffset(0)
  }, [auditMode, search])

  useEffect(() => {
    if (!campaignId) {
      setAuditData(null)
      setAuditError('')
      return
    }
    if (auditMode === 'off') {
      setAuditData(null)
      setAuditError('')
      return
    }
    const reqId = auditRequestRef.current + 1
    auditRequestRef.current = reqId
    setIsAuditLoading(true)
    setAuditError('')
    const gapOptions = auditMode === 'no_matches'
      ? { matchGapFilter: 'contacts_no_match' as const }
      : { titleMatch: true }
    const trimmed = search.trim()
    listContactCompanies({
      campaignId,
      ...gapOptions,
      limit: AUDIT_PAGE_SIZE,
      offset: auditOffset,
      ...(trimmed ? { search: trimmed } : {}),
    })
      .then((response) => {
        if (auditRequestRef.current !== reqId) return
        setAuditData(response)
      })
      .catch((err) => {
        if (auditRequestRef.current !== reqId) return
        setAuditError(parseApiError(err))
      })
      .finally(() => {
        if (auditRequestRef.current === reqId) setIsAuditLoading(false)
      })
  }, [auditMode, auditOffset, campaignId, search])

  const isAuditActive = auditMode !== 'off'
  const auditItems = auditData?.items ?? []
  const auditTotal = auditData?.total ?? null
  const auditHasMore = auditData?.has_more ?? false

  const visibleCompanies = (companies?.items ?? []).filter((c) => {
    if (search && !c.domain.toLowerCase().includes(search.toLowerCase())) return false
    const letterOk = activeLetters.size === 0 || activeLetters.has(c.domain[0].toLowerCase())
    return letterOk
  })

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  const isSearchFiltered = search !== ''
  const displayCount = isSearchFiltered ? visibleCompanies.length : (companies?.total ?? 0)
  const effectiveTotalMatching = isSearchFiltered ? visibleCompanies.length : totalMatching
  const contactFetch = stats?.contact_fetch
  const cfRunning = contactFetch?.running ?? 0
  const cfQueued = contactFetch?.queued ?? 0
  const cfCompleted = contactFetch?.completed ?? 0
  const cfFailed = contactFetch?.failed ?? 0
  const cfTotal = contactFetch?.total ?? 0
  const cfPct = contactFetch?.pct_done ?? 0
  const cfProcessed = cfCompleted + cfFailed
  const cfHasActivity = cfRunning > 0 || cfQueued > 0

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 space-y-2 pb-1" style={{ backgroundColor: 'var(--oc-bg)' }}>
      {contactFetch && (cfHasActivity || cfCompleted > 0 || cfFailed > 0) && (
        <div className="rounded-2xl border border-(--oc-border) bg-white p-4 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-(--oc-muted)">
                Contact Fetch Queue
              </span>
              {cfHasActivity && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                  Active
                </span>
              )}
            </div>
            <span className="text-[11px] text-(--oc-muted)">
              {cfProcessed.toLocaleString()} / {cfTotal.toLocaleString()} processed
            </span>
          </div>
          <p className="mb-2 text-[11px] text-(--oc-muted)">
            <RelativeTimeLabel timestamp={stats?.as_of} />
          </p>
          <div className="h-1.5 overflow-hidden rounded-full bg-(--oc-surface)" style={{ border: '1px solid var(--oc-border)' }}>
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(cfPct, 100)}%`,
                background: cfHasActivity ? 'linear-gradient(90deg, var(--s3), #0ea5e9)' : '#16a34a',
              }}
            />
          </div>
          <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-[11px]">
            {cfRunning > 0 && <span className="font-bold text-amber-600">{cfRunning.toLocaleString()} <span className="font-normal text-(--oc-muted)">running</span></span>}
            {cfQueued > 0 && <span className="font-bold text-(--oc-muted)">{cfQueued.toLocaleString()} <span className="font-normal">queued</span></span>}
            <span className="font-bold text-emerald-700">{cfCompleted.toLocaleString()} <span className="font-normal text-(--oc-muted)">done</span></span>
            {cfFailed > 0 && <span className="font-bold text-rose-600">{cfFailed.toLocaleString()} <span className="font-normal text-(--oc-muted)">failed</span></span>}
          </div>
        </div>
      )}
      {/* Header */}
      <div className="flex items-center gap-2 rounded-xl px-3 py-2.5" style={{ borderLeft: '3px solid var(--s3)', backgroundColor: 'var(--s3-bg)' }}>
        <div className="flex-1">
          <h2 className="text-base font-bold" style={{ color: 'var(--s3-text)' }}>S3 · Contact Fetch</h2>
          <p className="text-xs" style={{ color: 'var(--s3-text)', opacity: 0.7 }}>
            Find contacts at any company · {companies != null ? `${displayCount.toLocaleString()} companies` : '—'}
          </p>
        </div>
        {/* Search */}
        <div className="relative">
          <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search domains…"
            className="rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--s3) focus:bg-white"
            style={{ width: 180 }}
          />
        </div>
        <button
          type="button"
          onClick={onOpenTitleRules}
          className="rounded-lg border border-(--oc-border) px-3 py-1.5 text-xs font-medium transition hover:border-(--s3) hover:text-(--s3-text) whitespace-nowrap"
        >
          Title Rules
        </button>
      </div>

      {/* Contact stats bar */}
      {contactCounts && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Total contacts', value: contactCounts.total, color: '#14532d', bg: '#dcfce7' },
            { label: 'Verified', value: contactCounts.verified, color: '#0369a1', bg: '#dbeafe' },
            { label: 'Eligible to verify', value: contactCounts.eligible_verify, color: '#6b21a8', bg: '#f3e8ff' },
            { label: 'Campaign ready', value: contactCounts.campaign_ready, color: '#92400e', bg: '#fef3c7' },
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
        />
      )}

      {/* Title-match audit chips — lets ops verify whether title rules catch the intended contacts */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-(--oc-muted)">Title-match audit</span>
        {([
          { value: 'off', label: 'Off' },
          { value: 'no_matches', label: 'Fetched · 0 matches' },
          { value: 'matched', label: 'Fetched · has matches' },
        ] as const).map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => setAuditMode(value)}
            className="rounded-full border px-3 py-1 text-xs font-medium transition"
            style={
              auditMode === value
                ? { borderColor: 'var(--s3)', backgroundColor: 'var(--s3-bg)', color: 'var(--s3-text)', fontWeight: 700 }
                : { borderColor: 'var(--oc-border)', color: 'var(--oc-muted)' }
            }
          >
            {label}
          </button>
        ))}
        {isAuditActive && (
          <span className="ml-1 text-[11px] text-(--oc-muted)">
            {auditMode === 'no_matches'
              ? 'Companies whose fetched contacts contain zero title matches — audit the match criteria.'
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
                  className="rounded-full border px-3 py-1 text-xs font-medium transition"
                  style={
                    decisionFilter === value
                      ? { borderColor: 'var(--s3)', backgroundColor: 'var(--s3-bg)', color: 'var(--s3-text)', fontWeight: 700 }
                      : { borderColor: 'var(--oc-border)', color: 'var(--oc-muted)' }
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <Pager offset={offset} pageSize={pageSize} total={companies?.total ?? null} hasMore={companies?.has_more ?? false} onPrev={onPagePrev} onNext={onPageNext} onPageSizeChange={onPageSizeChange} />
          </div>

          <SelectionBar
            stageColor="--s3"
            stageBg="--s3-bg"
            selectedCount={selectedIds.length}
            totalMatching={effectiveTotalMatching}
            activeLetters={activeLetters}
            onSelectAllMatching={selectedIds.length > 0 && !isSearchFiltered ? onSelectAllMatching : null}
            isSelectingAll={isSelectingAll}
            onClear={onClearSelection}
          >
            {FETCH_BUTTONS.map(({ source, label, bg }) => (
              <button
                key={source}
                type="button"
                onClick={() => onFetchSelected(source)}
                disabled={isFetching || selectedIds.length === 0}
                className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
                style={{ backgroundColor: bg }}
              >
                {isFetching ? '…' : label}
              </button>
            ))}
            <span className="text-[11px] text-(--oc-muted)">
              Both = sequential chain (Snov first, Apollo second) to avoid parallel provider spend.
            </span>
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
              onClick={onOpenTitleRules}
              className="rounded-lg border border-(--oc-border) px-3 py-1.5 text-xs font-medium transition hover:border-(--s3) hover:text-(--s3-text)"
            >
              Edit title rules
            </button>
            <button
              type="button"
              disabled={auditOffset === 0}
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
              disabled={!auditHasMore}
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
          {auditError && (
            <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-xs text-red-700">{auditError}</div>
          )}
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-(--oc-border) text-xs text-(--oc-muted)">
                <th className="p-3 text-left font-semibold">Domain</th>
                <th className="p-3 text-right font-semibold">Contacts</th>
                <th className="p-3 text-right font-semibold">Title matched</th>
                <th className="p-3 text-right font-semibold">With email</th>
                <th className="p-3 text-right font-semibold">Last fetched</th>
                <th className="p-3 text-left font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {isAuditLoading && Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-(--oc-border)">
                  <td className="p-3"><div className="oc-skeleton h-4 w-36 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-8 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-8 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-8 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton ml-auto h-4 w-20 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-6 w-16 rounded-lg" /></td>
                </tr>
              ))}
              {!isAuditLoading && auditItems.length === 0 && !auditError && (
                <tr>
                  <td colSpan={6} className="px-6 py-10 text-center">
                    <p className="text-sm font-semibold text-(--oc-text)">
                      {auditMode === 'no_matches'
                        ? 'No companies with fetched contacts and zero title matches.'
                        : 'No companies have title-matched contacts yet.'}
                    </p>
                    <p className="mt-1 text-xs text-(--oc-muted)">
                      {auditMode === 'no_matches'
                        ? 'Either the match criteria are catching everything or contacts have not been fetched.'
                        : 'Try fetching contacts for more companies or broadening your title rules.'}
                    </p>
                  </td>
                </tr>
              )}
              {!isAuditLoading && auditItems.map((summary) => {
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
                        className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s3) hover:text-(--s3-text)"
                      >
                        View contacts
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
                  checked={allVisibleSelected}
                  ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                  onChange={() => onToggleAll(allVisibleSelected ? [] : visibleCompanies.map((c) => c.id))}
                  className="cursor-pointer"
                />
              </th>
              <SortableHeader label="Domain" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Decision" field="decision" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Contacts" field="contact_count" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <th className="p-3 text-left font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 8 }).map((_, i) => (
              <tr key={i} className="border-b border-(--oc-border)">
                <td className="p-3"><div className="oc-skeleton h-4 w-4 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-36 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-5 w-16 rounded-full" /></td>
                <td className="p-3"><div className="oc-skeleton h-4 w-8 rounded" /></td>
                <td className="p-3"><div className="oc-skeleton h-6 w-20 rounded-lg" /></td>
              </tr>
            ))}
            {!isLoading && visibleCompanies.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-10 text-center">
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
              <tr
                key={c.id}
                className="border-b border-(--oc-border) last:border-0 transition"
                style={selectedSet.has(c.id) ? { backgroundColor: 'var(--s3-bg)' } : {}}
              >
                <td className="p-3">
                  <input
                    type="checkbox"
                    checked={selectedSet.has(c.id)}
                    onChange={() => onToggleRow(c.id)}
                    className="cursor-pointer"
                  />
                </td>
                <td className="p-3">
                  <a
                    href={c.normalized_url || c.raw_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[12px] font-medium hover:underline"
                    style={{ color: 'var(--s3)' }}
                  >
                    {c.domain}
                  </a>
                </td>
                <td className="p-3">
                  {(c.feedback_manual_label ?? c.latest_decision) ? (
                    <Badge className={decisionBgClass(c.feedback_manual_label ?? c.latest_decision)}>
                      {c.feedback_manual_label ?? c.latest_decision}
                    </Badge>
                  ) : <span className="text-xs text-(--oc-muted)">—</span>}
                </td>
                <td className="p-3 text-xs font-mono">{c.contact_count ?? 0}</td>
                <td className="p-3">
                  <div className="flex flex-wrap gap-1">
                    <button
                      type="button"
                      onClick={() => onViewContacts(c)}
                      disabled={(c.contact_count ?? 0) === 0}
                      className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s3) hover:text-(--s3-text) disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      View
                    </button>
                    <button
                      type="button"
                      onClick={() => onFetchOne(c, 'both')}
                      title="Sequential chain: Snov first, Apollo follow-up."
                      className="rounded-lg px-2.5 py-1.5 text-[11px] font-bold text-white transition"
                      style={{ backgroundColor: 'var(--s3)' }}
                    >
                      Both
                    </button>
                    <button
                      type="button"
                      onClick={() => onFetchOne(c, 'snov')}
                      className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s3) hover:text-(--s3-text)"
                    >
                      Snov
                    </button>
                    <button
                      type="button"
                      onClick={() => onFetchOne(c, 'apollo')}
                      className="rounded-lg border border-(--oc-border) px-2.5 py-1.5 text-[11px] font-medium transition hover:border-(--s3) hover:text-(--s3-text)"
                    >
                      Apollo
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}
