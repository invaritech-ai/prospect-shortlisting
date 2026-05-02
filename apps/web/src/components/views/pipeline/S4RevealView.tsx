import { useState } from 'react'
import type {
  DiscoveredContactCountsResponse,
  DiscoveredContactListResponse,
  DiscoveredContactRead,
} from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { SortableHeader } from '../../ui/SortableHeader'
import { Pager } from '../../ui/Pager'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'

interface S4RevealViewProps {
  contacts: DiscoveredContactListResponse | null
  counts: DiscoveredContactCountsResponse | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  selectedIds: string[]
  matchFilter: 'all' | 'matched' | 'unmatched'
  search: string
  isSelectingAll: boolean
  sortBy: string
  sortDir: 'asc' | 'desc'
  onMatchFilterChange: (f: 'all' | 'matched' | 'unmatched') => void
  onSearchChange: (value: string) => void
  onToggleLetter: (letter: string) => void
  onClearLetters: () => void
  onToggle: (id: string) => void
  onToggleAll: (ids: string[]) => void
  staleEmailOnly: boolean
  onStaleEmailOnlyChange: (v: boolean) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onRevealSelected: () => void
  onOpenTitleRules: () => void
  offset: number
  pageSize: number
  onPagePrev: () => void
  onPageNext: () => void
  onPageSizeChange: (size: number) => void
  onSort: (field: string) => void
  isLoading: boolean
  isRevealing: boolean
}

const MATCH_FILTERS: Array<{ value: 'all' | 'matched' | 'unmatched'; label: string }> = [
  { value: 'all', label: 'All contacts' },
  { value: 'matched', label: 'Title matched' },
  { value: 'unmatched', label: 'Unmatched' },
]

function ProviderBadge({ provider }: { provider: string }) {
  const color = provider === 'apollo' ? '#15803d' : '#0369a1'
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"
      style={{ backgroundColor: color }}
    >
      {provider}
    </span>
  )
}

function TitleMatchBadge({ matched }: { matched: boolean }) {
  return matched ? (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ backgroundColor: 'var(--s4-bg)', color: 'var(--s4-text)' }}
    >
      Matched
    </span>
  ) : (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ backgroundColor: 'var(--oc-surface)', color: 'var(--oc-muted)', border: '1px solid var(--oc-border)' }}
    >
      Unmatched
    </span>
  )
}

function FreshnessBadge({ status }: { status: 'fresh' | 'stale' }) {
  return status === 'fresh' ? (
    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-green-700" style={{ backgroundColor: '#dcfce7' }}>
      Fresh
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-amber-700" style={{ backgroundColor: '#fef3c7' }}>
      Stale
    </span>
  )
}

function HasEmailBadge({ value }: { value: boolean | null }) {
  if (value === true) {
    return (
      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-emerald-700" style={{ backgroundColor: '#dcfce7' }}>
        Yes
      </span>
    )
  }
  if (value === false) {
    return (
      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold text-slate-700" style={{ backgroundColor: '#f1f5f9' }}>
        No
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ backgroundColor: 'var(--oc-surface)', color: 'var(--oc-muted)', border: '1px solid var(--oc-border)' }}
    >
      Unknown
    </span>
  )
}

export function S4RevealView({
  contacts,
  counts,
  letterCounts,
  activeLetters,
  selectedIds,
  matchFilter,
  search,
  isSelectingAll,
  sortBy,
  sortDir,
  onMatchFilterChange,
  onSearchChange,
  onToggleLetter,
  staleEmailOnly,
  onStaleEmailOnlyChange,
  onClearLetters,
  onToggle,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onRevealSelected,
  onOpenTitleRules,
  offset,
  pageSize,
  onPagePrev,
  onPageNext,
  onPageSizeChange,
  onSort,
  isLoading,
  isRevealing,
}: S4RevealViewProps) {
  const [showRevealConfirm, setShowRevealConfirm] = useState(false)
  const controlsDisabled = isLoading || isRevealing
  const visibleContacts: DiscoveredContactRead[] = contacts?.items ?? []
  const selectedSet = new Set(selectedIds)
  const visibleIds = visibleContacts.map((contact) => contact.id)
  const allVisibleSelected =
    visibleContacts.length > 0 && visibleContacts.every((contact) => selectedSet.has(contact.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleContacts.some((contact) => selectedSet.has(contact.id))
  const hasActiveFilters =
    matchFilter !== 'all' ||
    activeLetters.size > 0 ||
    search.trim().length > 0

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 space-y-2 pb-1" style={{ backgroundColor: 'var(--oc-bg)' }}>
        <div className="rounded-xl px-3 py-2.5" style={{ borderLeft: '3px solid var(--s4)', backgroundColor: 'var(--s4-bg)' }}>
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <h2 className="text-base font-bold" style={{ color: 'var(--s4-text)' }}>S4 · Reveal</h2>
              <p className="text-xs" style={{ color: 'var(--s4-text)', opacity: 0.74 }}>
                Match discovered contacts to title rules, then reveal email addresses for the right people.
              </p>
            </div>
            <div className="relative">
              <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-(--oc-muted)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                disabled={controlsDisabled}
                placeholder="Search contacts or domains…"
                className="rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--s4) focus:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                style={{ width: 220 }}
              />
            </div>
            <button
              type="button"
              onClick={onOpenTitleRules}
              disabled={controlsDisabled}
              className="rounded-lg border border-(--oc-border) px-3 py-1.5 text-xs font-medium transition hover:border-(--s4) hover:text-(--s4-text) whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-60"
            >
              Edit title rules
            </button>
          </div>
        </div>

        {counts && (
          <div className="flex flex-wrap gap-2">
            {[
              { label: 'Discovered', value: counts.total, color: 'var(--s4-text)', borderColor: 'var(--s4)', bg: 'var(--s4-bg)' },
              { label: 'Title matched', value: counts.matched, color: '#0f766e', borderColor: '#0f766e', bg: '#ccfbf1' },
              { label: 'Fresh', value: counts.fresh, color: '#15803d', borderColor: '#15803d', bg: '#dcfce7' },
              { label: 'Stale', value: counts.stale, color: '#b45309', borderColor: '#b45309', bg: '#fef3c7' },
              { label: 'Already revealed', value: counts.already_revealed, color: '#6b21a8', borderColor: '#6b21a8', bg: '#f3e8ff' },
            ].map(({ label, value, color, borderColor, bg }) => (
              <div
                key={label}
                className="rounded-xl border px-3 py-1.5 text-xs"
                style={{ borderColor, backgroundColor: bg }}
              >
                <span className="font-black tabular-nums" style={{ color }}>{(value ?? 0).toLocaleString()}</span>
                <span className="ml-1.5" style={{ color }}>{label}</span>
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
          disabled={controlsDisabled}
        />

        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5">
            {MATCH_FILTERS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => onMatchFilterChange(value)}
                disabled={controlsDisabled}
                className={`rounded-full px-3 py-1 text-[11px] font-bold transition disabled:opacity-50 disabled:cursor-not-allowed ${
                  matchFilter === value
                    ? 'text-white'
                    : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s4) hover:text-(--s4-text)'
                }`}
                style={matchFilter === value ? { backgroundColor: 'var(--s4)' } : {}}
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => onStaleEmailOnlyChange(!staleEmailOnly)}
              disabled={controlsDisabled}
              className={`rounded-full px-3 py-1 text-[11px] font-bold transition disabled:opacity-50 disabled:cursor-not-allowed ${
                staleEmailOnly
                  ? 'text-white'
                  : 'border border-(--oc-border) text-(--oc-muted) hover:border-amber-500 hover:text-amber-600'
              }`}
              style={staleEmailOnly ? { backgroundColor: '#b45309' } : {}}
            >
              Stale email (&gt;30d)
            </button>
          </div>
          <Pager
            offset={offset}
            pageSize={pageSize}
            total={contacts?.total ?? null}
            hasMore={contacts?.has_more ?? false}
            onPrev={onPagePrev}
            onNext={onPageNext}
            onPageSizeChange={onPageSizeChange}
            disabled={controlsDisabled}
          />
        </div>

        <SelectionBar
          stageColor="--s4"
          stageBg="--s4-bg"
          selectedCount={selectedIds.length}
          totalMatching={contacts?.total ?? null}
          activeLetters={activeLetters}
          onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
          isSelectingAll={isSelectingAll}
          onClear={onClearSelection}
          disabled={controlsDisabled}
        >
          <button
            type="button"
            onClick={() => setShowRevealConfirm(true)}
            disabled={selectedIds.length === 0 || isRevealing}
            className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
            style={{ backgroundColor: 'var(--s4)' }}
          >
            {isRevealing ? 'Revealing…' : 'Reveal Emails'}
          </button>
        </SelectionBar>
      </div>

      {isLoading && (
        <div className="oc-panel overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {Array.from({ length: 8 }).map((_, index) => (
                <tr key={index} className="border-b border-(--oc-border) last:border-0">
                  <td className="p-3"><div className="oc-skeleton h-4 w-4 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-24 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-24 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-20 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-28 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-5 w-16 rounded-full" /></td>
                  <td className="p-3"><div className="oc-skeleton h-5 w-14 rounded-full" /></td>
                  <td className="p-3"><div className="oc-skeleton h-5 w-14 rounded-full" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-16 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-20 rounded" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!isLoading && visibleContacts.length === 0 && (
        <div className="rounded-2xl border border-(--oc-border) bg-white px-6 py-10 text-center">
          {hasActiveFilters ? (
            <div className="space-y-1">
              <p className="text-sm font-semibold text-(--oc-text)">No discovered contacts match this filter.</p>
              <p className="text-xs text-(--oc-muted)">Adjust the title-match filter, search, or letter selection to broaden the list.</p>
            </div>
          ) : (
            <div className="space-y-1">
              <p className="text-sm font-semibold text-(--oc-text)">No discovered contacts yet</p>
              <p className="text-xs text-(--oc-muted)">Run S3 contact discovery first, then come back here to review and reveal emails.</p>
            </div>
          )}
        </div>
      )}

      {!isLoading && visibleContacts.length > 0 && (
        <div className="oc-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-(--oc-border) text-[10px] uppercase tracking-wider text-(--oc-muted)">
                <th className="w-8 p-3">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    disabled={controlsDisabled}
                    ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                    onChange={() => onToggleAll(allVisibleSelected ? [] : visibleIds)}
                    className="cursor-pointer disabled:cursor-not-allowed"
                  />
                </th>
                <SortableHeader label="Contact" field="first_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
                <SortableHeader label="Company" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
                <SortableHeader label="Last seen" field="last_seen_at" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
                <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
                <SortableHeader label="Provider" field="provider" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
                <SortableHeader label="Title match" field="title_match" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
                <SortableHeader label="Has email" field="provider_has_email" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
                <th className="p-3 text-left font-semibold">Freshness</th>
                <SortableHeader label="Discovered" field="created_at" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={controlsDisabled} />
              </tr>
            </thead>
            <tbody>
              {visibleContacts.map((contact) => {
                const fullName = [contact.first_name, contact.last_name].filter(Boolean).join(' ') || '—'
                return (
                  <tr
                    key={contact.id}
                    className="border-b border-(--oc-border) last:border-0 transition hover:bg-(--oc-surface)"
                    style={selectedSet.has(contact.id) ? { backgroundColor: 'var(--s4-bg)' } : {}}
                    onClick={() => { if (!controlsDisabled) onToggle(contact.id) }}
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={selectedSet.has(contact.id)}
                        disabled={controlsDisabled}
                        onChange={() => onToggle(contact.id)}
                        onClick={(event) => event.stopPropagation()}
                        className="cursor-pointer disabled:cursor-not-allowed"
                      />
                    </td>
                    <td className="p-3">
                      <div className="font-semibold text-sm">{fullName}</div>
                      {contact.linkedin_url && (
                        <a
                          href={contact.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] hover:underline"
                          style={{ color: 'var(--s4-text)' }}
                          onClick={(event) => event.stopPropagation()}
                        >
                          LinkedIn
                        </a>
                      )}
                    </td>
                    <td className="p-3">
                      <a
                        href={`https://${contact.domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-[11px] font-medium hover:underline"
                        style={{ color: 'var(--s4-text)' }}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {contact.domain}
                      </a>
                    </td>
                    <td className="p-3 text-[11px] text-(--oc-muted)">
                      <RelativeTimeLabel timestamp={contact.last_seen_at} prefix="" />
                    </td>
                    <td className="p-3 text-(--oc-muted)">{contact.title ?? '—'}</td>
                    <td className="p-3">
                      <ProviderBadge provider={contact.source_provider} />
                    </td>
                    <td className="p-3">
                      <TitleMatchBadge matched={contact.title_match} />
                    </td>
                    <td className="p-3">
                      <HasEmailBadge value={contact.provider_has_email} />
                    </td>
                    <td className="p-3">
                      <FreshnessBadge status={contact.freshness_status} />
                    </td>
                    <td className="p-3 text-[11px] text-(--oc-muted)">
                      <RelativeTimeLabel timestamp={contact.created_at} prefix="" />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={showRevealConfirm}
        title="Reveal email addresses?"
        confirmLabel="Reveal"
        isConfirming={isRevealing}
        onClose={() => setShowRevealConfirm(false)}
        onConfirm={() => {
          setShowRevealConfirm(false)
          onRevealSelected()
        }}
      >
        <p className="text-sm text-(--oc-muted)">
          This will fetch email addresses for{' '}
          <strong className="text-(--oc-text)">{selectedIds.length} contact{selectedIds.length !== 1 ? 's' : ''}</strong>{' '}
          using Snov.io and/or Apollo credits. This action cannot be undone.
        </p>
      </ConfirmDialog>
    </div>
  )
}
