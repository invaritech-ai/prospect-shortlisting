import { useState } from 'react'
import type { CompanyList, CompanyListItem, ContactCountsResponse, DecisionFilter } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { decisionBgClass } from '../../ui/badgeUtils'
import { SortableHeader } from '../../ui/SortableHeader'
import { Pager } from '../../ui/Pager'

interface S3ContactFetchViewProps {
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
  onDecisionFilterChange: (filter: DecisionFilter) => void
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onFetchOne: (company: CompanyListItem, source: 'snov' | 'apollo' | 'both') => void
  onFetchSelected: (source: 'snov' | 'apollo' | 'both') => void
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
  onDecisionFilterChange,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onFetchOne,
  onFetchSelected,
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

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 space-y-2 pb-1" style={{ backgroundColor: 'var(--oc-bg)' }}>
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

      <LetterStrip
        multiSelect
        activeLetters={activeLetters}
        counts={letterCounts}
        onToggle={onToggleLetter}
        onClear={onClearLetters}
      />

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
      </SelectionBar>
      </div>{/* ── /sticky controls ── */}

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
              <th className="p-3 text-left font-semibold">Fetch</th>
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
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => onFetchOne(c, 'both')}
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
    </div>
  )
}
