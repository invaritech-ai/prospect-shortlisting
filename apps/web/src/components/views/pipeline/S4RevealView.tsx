import { useState } from 'react'
import type { DiscoveredContactListResponse, DiscoveredContactCountsResponse, DiscoveredContactRead } from '../../../lib/types'
import { SelectionBar } from '../../ui/SelectionBar'
import { Pager } from '../../ui/Pager'
import { ConfirmDialog } from '../../ui/ConfirmDialog'

interface S4RevealViewProps {
  campaignId: string | null
  contacts: DiscoveredContactListResponse | null
  counts: DiscoveredContactCountsResponse | null
  selectedIds: string[]
  matchFilter: 'all' | 'matched' | 'unmatched'
  onMatchFilterChange: (f: 'all' | 'matched' | 'unmatched') => void
  onToggle: (id: string) => void
  onToggleAll: (ids: string[]) => void
  onClearSelection: () => void
  onRevealSelected: () => void
  onOpenTitleRules: () => void
  offset: number
  pageSize: number
  onPagePrev: () => void
  onPageNext: () => void
  isLoading: boolean
  isRevealing: boolean
}

const MATCH_FILTERS: Array<{ value: 'all' | 'matched' | 'unmatched'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'matched', label: 'Title matched' },
  { value: 'unmatched', label: 'Unmatched' },
]

function ProviderBadge({ provider }: { provider: string }) {
  const color = provider === 'apollo' ? '#15803d' : '#0369a1'
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold text-white"
      style={{ backgroundColor: color }}
    >
      {provider}
    </span>
  )
}

function TitleMatchBadge({ matched }: { matched: boolean }) {
  return matched ? (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ backgroundColor: 'var(--s4-bg)', color: 'var(--s4-text)' }}>
      Yes
    </span>
  ) : (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ backgroundColor: 'var(--oc-surface)', color: 'var(--oc-muted)', border: '1px solid var(--oc-border)' }}>
      No
    </span>
  )
}

function FreshnessBadge({ status }: { status: 'fresh' | 'stale' }) {
  return status === 'fresh' ? (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold text-green-700" style={{ backgroundColor: '#dcfce7' }}>
      Fresh
    </span>
  ) : (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold text-amber-700" style={{ backgroundColor: '#fef3c7' }}>
      Stale
    </span>
  )
}

function hasEmailLabel(val: boolean | null): string {
  if (val === true) return 'Yes'
  if (val === false) return 'No'
  return '—'
}

export function S4RevealView({
  contacts,
  counts,
  selectedIds,
  matchFilter,
  onMatchFilterChange,
  onToggle,
  onToggleAll,
  onClearSelection,
  onRevealSelected,
  onOpenTitleRules,
  offset,
  pageSize,
  onPagePrev,
  onPageNext,
  isLoading,
  isRevealing,
}: S4RevealViewProps) {
  const [showRevealConfirm, setShowRevealConfirm] = useState(false)
  const items: DiscoveredContactRead[] = contacts?.items ?? []
  const visibleIds = items.map((c) => c.id)
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id))

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 space-y-2 pb-1" style={{ backgroundColor: 'var(--oc-bg)' }}>
        {/* Header card */}
        <div className="rounded-xl px-3 py-2.5" style={{ borderLeft: '3px solid var(--s4)', backgroundColor: 'var(--s4-bg)' }}>
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <h2 className="text-base font-bold" style={{ color: 'var(--s4-text)' }}>S4 · Reveal</h2>
              <p className="text-xs" style={{ color: 'var(--s4-text)', opacity: 0.7 }}>
                Match titles and reveal emails · {counts?.total ?? 0} discovered · {counts?.matched ?? 0} title matched · {counts?.already_revealed ?? 0} already revealed
              </p>
            </div>
            <button
              type="button"
              onClick={onOpenTitleRules}
              disabled={isLoading}
              className="rounded-lg border border-(--oc-border) px-3 py-1.5 text-xs font-medium transition hover:border-(--s4) hover:text-(--s4-text) whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-60"
            >
              Edit title rules
            </button>
          </div>
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-2">
          {MATCH_FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => onMatchFilterChange(value)}
              disabled={isLoading}
              className="rounded-full border px-3 py-1 text-xs font-medium transition disabled:opacity-50 disabled:cursor-not-allowed"
              style={
                matchFilter === value
                  ? { backgroundColor: 'var(--s4)', color: '#fff', borderColor: 'var(--s4)' }
                  : { borderColor: 'var(--oc-border)', color: 'var(--oc-muted)' }
              }
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-12 text-sm text-(--oc-muted)">Loading…</div>
      )}

      {/* Empty state */}
      {!isLoading && items.length === 0 && (
        <div className="flex items-center justify-center py-12 text-sm text-(--oc-muted)">
          No discovered contacts yet. Run S3 contact fetch first.
        </div>
      )}

      {/* Table */}
      {!isLoading && items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-(--oc-border)">
          <table className="w-full text-sm">
            <thead className="border-b border-(--oc-border) bg-(--oc-surface)">
              <tr>
                <th className="w-10 p-3">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={() => onToggleAll(visibleIds)}
                    disabled={isLoading || isRevealing}
                    className="cursor-pointer"
                  />
                </th>
                <th className="p-3 text-left font-semibold">Name</th>
                <th className="p-3 text-left font-semibold">Title</th>
                <th className="p-3 text-left font-semibold">Company</th>
                <th className="p-3 text-left font-semibold">Provider</th>
                <th className="p-3 text-left font-semibold">Title Match</th>
                <th className="p-3 text-left font-semibold">Has Email</th>
                <th className="p-3 text-left font-semibold">Freshness</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-(--oc-border)">
              {items.map((contact) => (
                <tr
                  key={contact.id}
                  className="cursor-pointer hover:bg-(--oc-surface-hover)"
                  onClick={() => onToggle(contact.id)}
                >
                  <td className="p-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(contact.id)}
                      onChange={() => onToggle(contact.id)}
                      onClick={(e) => e.stopPropagation()}
                      disabled={isLoading || isRevealing}
                      className="cursor-pointer"
                    />
                  </td>
                  <td className="p-3 font-medium">
                    {contact.first_name} {contact.last_name}
                  </td>
                  <td className="p-3 text-(--oc-muted)">{contact.title ?? '—'}</td>
                  <td className="p-3 text-(--oc-muted)">{contact.domain}</td>
                  <td className="p-3">
                    <ProviderBadge provider={contact.provider} />
                  </td>
                  <td className="p-3">
                    <TitleMatchBadge matched={contact.title_match} />
                  </td>
                  <td className="p-3 text-(--oc-muted) text-xs">{hasEmailLabel(contact.provider_has_email)}</td>
                  <td className="p-3">
                    <FreshnessBadge status={contact.freshness_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination + selection bar */}
      {!isLoading && items.length > 0 && (
        <div className="flex items-center justify-between">
          <Pager
            offset={offset}
            pageSize={pageSize}
            total={contacts?.total ?? null}
            hasMore={contacts?.has_more ?? false}
            onPrev={onPagePrev}
            onNext={onPageNext}
            disabled={isLoading}
          />
        </div>
      )}

      <SelectionBar
        stageColor="--s4"
        stageBg="--s4-bg"
        selectedCount={selectedIds.length}
        totalMatching={contacts?.total ?? 0}
        activeLetters={new Set()}
        onSelectAllMatching={null}
        isSelectingAll={false}
        onClear={onClearSelection}
        disabled={isLoading || isRevealing}
      >
        <button
          type="button"
          onClick={() => setShowRevealConfirm(true)}
          disabled={selectedIds.length === 0 || isRevealing}
          className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
          style={{ backgroundColor: 'var(--s4)' }}
        >
          {isRevealing ? '…' : 'Reveal Emails'}
        </button>
      </SelectionBar>

      <ConfirmDialog
        open={showRevealConfirm}
        title="Reveal email addresses?"
        confirmLabel="Reveal"
        isConfirming={isRevealing}
        onClose={() => setShowRevealConfirm(false)}
        onConfirm={() => { setShowRevealConfirm(false); onRevealSelected() }}
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
