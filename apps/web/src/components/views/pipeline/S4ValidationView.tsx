import { useState } from 'react'
import type {
  ContactCountsResponse,
  ContactListResponse,
  ProspectContactRead,
  S4VerifFilter,
  StatsResponse,
} from '../../../lib/types'
import { parseUTC } from '../../../lib/api'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { SortableHeader } from '../../ui/SortableHeader'
import { Pager } from '../../ui/Pager'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'

interface S4ValidationViewProps {
  contacts: ContactListResponse | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  verifFilter: S4VerifFilter
  selectedContactIds: string[]
  totalMatching: number | null
  contactCounts: ContactCountsResponse | null
  stats: StatsResponse | null
  isLoading: boolean
  isValidating: boolean
  isSelectingAll: boolean
  exportUrl: string
  onVerifFilterChange: (filter: S4VerifFilter) => void
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleContact: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onValidateSelected: () => void
  offset: number
  pageSize: number
  onPagePrev: () => void
  onPageNext: () => void
  onPageSizeChange: (size: number) => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
}

const VERIF_FILTERS: Array<{ value: S4VerifFilter; label: string; color?: string }> = [
  { value: 'all', label: 'All contacts' },
  { value: 'valid', label: 'Valid', color: '#15803d' },
  { value: 'invalid', label: 'Invalid', color: '#dc2626' },
  { value: 'catch-all', label: 'Catch-all', color: '#d97706' },
  { value: 'unverified', label: 'Unverified' },
  { value: 'campaign_ready', label: 'Campaign ready', color: '#6b21a8' },
  { value: 'title_match', label: 'Title match only' },
  { value: 'stale_30d', label: 'Stale >30d', color: '#b45309' },
]

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000

function getLastValidatedAt(contact: ProspectContactRead): Date | null {
  if (!contact.verification_status || contact.verification_status.toLowerCase() === 'unverified') return null
  if (contact.pipeline_stage !== 'email_revealed' && contact.pipeline_stage !== 'campaign_ready') return null
  return parseUTC(contact.updated_at)
}

function isStaleOver30Days(contact: ProspectContactRead): boolean {
  const validatedAt = getLastValidatedAt(contact)
  if (!validatedAt) return false
  return (Date.now() - validatedAt.getTime()) > THIRTY_DAYS_MS
}

function verifBadge(contact: ProspectContactRead) {
  const s = contact.verification_status?.toLowerCase() ?? ''
  if (s === 'valid') return { label: 'Valid', bg: '#dcfce7', text: '#14532d', dot: '#15803d' }
  if (s === 'invalid') return { label: 'Invalid', bg: '#ffe4e6', text: '#9f1239', dot: '#dc2626' }
  if (s === 'catch-all' || s === 'catchall') return { label: 'Catch-all', bg: '#fef3c7', text: '#92400e', dot: '#d97706' }
  if (s === 'spamtrap' || s === 'abuse' || s === 'do_not_mail') return { label: s, bg: '#ffe4e6', text: '#9f1239', dot: '#dc2626' }
  return null
}

function stageBadge(contact: ProspectContactRead) {
  if (contact.pipeline_stage === 'campaign_ready') return { label: 'Campaign ready', bg: '#f3e8ff', text: '#581c87' }
  if (contact.pipeline_stage === 'email_revealed') return { label: 'Email revealed', bg: '#f1f5f9', text: '#334155' }
  if (contact.verification_status && contact.verification_status !== 'unverified') {
    return { label: 'Fetched', bg: '#fef3c7', text: '#92400e' }
  }
  return null
}

export function S4ValidationView({
  contacts,
  letterCounts,
  activeLetters,
  verifFilter,
  selectedContactIds,
  totalMatching,
  contactCounts,
  stats,
  isLoading,
  isValidating,
  isSelectingAll,
  exportUrl,
  onVerifFilterChange,
  onToggleLetter,
  onClearLetters,
  onToggleContact,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onValidateSelected,
  offset,
  pageSize,
  onPagePrev,
  onPageNext,
  onPageSizeChange,
  sortBy,
  sortDir,
  onSort,
}: S4ValidationViewProps) {
  const [showVerifyConfirm, setShowVerifyConfirm] = useState(false)
  const selectedSet = new Set(selectedContactIds)

  // Server applies both verification and letter filters for paginated correctness.
  const visibleContacts = contacts?.items ?? []

  const allVisibleSelected =
    visibleContacts.length > 0 && visibleContacts.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleContacts.some((c) => selectedSet.has(c.id))

  const displayCount = contacts?.total ?? visibleContacts.length
  const effectiveTotalMatching = totalMatching
  const validation = stats?.validation
  const vRunning = validation?.running ?? 0
  const vQueued = validation?.queued ?? 0
  const vCompleted = validation?.succeeded ?? 0
  const vFailed = validation?.failed ?? 0
  const vTotal = validation?.total ?? 0
  const vPct = validation?.pct_done ?? 0
  const vProcessed = vCompleted + vFailed
  const vHasActivity = vRunning > 0 || vQueued > 0

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 space-y-2 pb-1" style={{ backgroundColor: 'var(--oc-bg)' }}>
      {/* Header */}
      <div className="rounded-xl px-3 py-2.5" style={{ borderLeft: '3px solid var(--s5)', backgroundColor: 'var(--s5-bg)' }}>
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <h2 className="text-base font-bold" style={{ color: 'var(--s5-text)' }}>S5 · Validation</h2>
            <p className="text-xs" style={{ color: 'var(--s5-text)', opacity: 0.7 }}>
              Validate contact emails with ZeroBounce ·{' '}
              {contacts != null ? `${displayCount.toLocaleString()} contacts` : '—'}
            </p>
          </div>
          {exportUrl && (
            <a
              href={exportUrl}
              className="rounded-lg border px-3 py-1.5 text-xs font-medium transition"
              style={{ borderColor: 'var(--s5)', color: 'var(--s5-text)' }}
            >
              Export CSV
            </a>
          )}
        </div>
        {validation && (vHasActivity || vCompleted > 0 || vFailed > 0) && (
          <div className="mt-2 flex items-center gap-3 border-t border-(--oc-border) pt-1.5 text-xs text-(--oc-muted)">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${vHasActivity ? 'animate-pulse bg-amber-400' : 'bg-(--oc-border)'}`} />
            <span className="flex items-center gap-1">
              {vRunning > 0 && <span className="text-amber-600"><strong>{vRunning.toLocaleString()}</strong> running ·</span>}
              {vQueued > 0 && <span><strong>{vQueued.toLocaleString()}</strong> queued ·</span>}
              {vCompleted > 0 && <span className="text-emerald-600"><strong>{vCompleted.toLocaleString()}</strong> done</span>}
              {vFailed > 0 && <span className="text-red-500"> · <strong>{vFailed.toLocaleString()}</strong> failed</span>}
            </span>
            <div className="flex-1 h-1 overflow-hidden rounded-full bg-(--oc-border)">
              <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(vPct, 100)}%`, backgroundColor: 'var(--s5)' }} />
            </div>
            <span className="tabular-nums shrink-0">{vProcessed.toLocaleString()} / {vTotal.toLocaleString()}</span>
          </div>
        )}
      </div>

      {/* Stats bar */}
      {contactCounts && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Matched', value: contactCounts.matched, color: '#15803d', bg: '#dcfce7' },
            { label: 'Fresh', value: contactCounts.fresh, color: '#0f766e', bg: '#ccfbf1' },
            { label: 'Stale', value: contactCounts.stale, color: '#b45309', bg: '#fef3c7' },
            { label: 'Already revealed', value: contactCounts.already_revealed, color: '#6b21a8', bg: '#f3e8ff' },
          ].map(({ label, value, color, bg }) => (
            <div
              key={label}
              className="rounded-xl border px-3 py-1.5 text-xs"
              style={{ borderColor: color + '33', backgroundColor: bg }}
            >
              <span className="font-black tabular-nums" style={{ color }}>{(value ?? 0).toLocaleString()}</span>
              <span className="ml-1.5" style={{ color: color + 'bb' }}>{label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Letter strip */}
      <LetterStrip
        multiSelect
        activeLetters={activeLetters}
        counts={letterCounts}
        onToggle={onToggleLetter}
        onClear={onClearLetters}
        disabled={isLoading || isValidating}
      />

      {/* Verification filter chips + pager */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {VERIF_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => onVerifFilterChange(f.value)}
              disabled={isLoading}
              className={`rounded-full px-3 py-1 text-[11px] font-bold transition disabled:opacity-50 disabled:cursor-not-allowed ${
                verifFilter === f.value
                  ? 'text-white'
                  : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s5) hover:text-(--s5-text)'
              }`}
              style={
                verifFilter === f.value
                  ? { backgroundColor: f.color ?? 'var(--s5)' }
                  : {}
              }
            >
              {f.label}
            </button>
          ))}
        </div>
        <Pager offset={offset} pageSize={pageSize} total={contacts?.total ?? null} hasMore={contacts?.has_more ?? false} onPrev={onPagePrev} onNext={onPageNext} onPageSizeChange={onPageSizeChange} disabled={isLoading} />
      </div>

      {/* Selection bar */}
      <SelectionBar
        stageColor="--s5"
        stageBg="--s5-bg"
        selectedCount={selectedContactIds.length}
        totalMatching={effectiveTotalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedContactIds.length > 0 ? onSelectAllMatching : null}
        isSelectingAll={isSelectingAll}
        onClear={onClearSelection}
      >
        <button
          type="button"
          onClick={() => setShowVerifyConfirm(true)}
          disabled={isValidating || selectedContactIds.length === 0}
          className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
          style={{ backgroundColor: 'var(--s5)' }}
        >
          {isValidating ? 'Queuing…' : 'Validate with ZeroBounce'}
        </button>
      </SelectionBar>

      <ConfirmDialog
        open={showVerifyConfirm}
        title="Validate with ZeroBounce?"
        confirmLabel="Validate"
        isConfirming={isValidating}
        onClose={() => setShowVerifyConfirm(false)}
        onConfirm={() => { setShowVerifyConfirm(false); onValidateSelected() }}
      >
        <p className="text-sm text-(--oc-muted)">
          This will validate{' '}
          <strong className="text-(--oc-text)">{selectedContactIds.length} email{selectedContactIds.length !== 1 ? 's' : ''}</strong>{' '}
          using ZeroBounce credits. This action cannot be undone.
        </p>
      </ConfirmDialog>
      </div>{/* ── /sticky controls ── */}

      {/* Table */}
      {isLoading && (
        <div className="oc-panel overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b border-(--oc-border)">
                  <td className="p-3"><div className="oc-skeleton h-4 w-4 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-28 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-24 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-36 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-5 w-12 rounded-full" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-24 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-5 w-16 rounded-full" /></td>
                  <td className="p-3"><div className="oc-skeleton h-4 w-24 rounded" /></td>
                  <td className="p-3"><div className="oc-skeleton h-5 w-20 rounded-full" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!isLoading && visibleContacts.length === 0 && (
        <div className="rounded-2xl border border-(--oc-border) bg-white px-6 py-10 text-center">
          {verifFilter === 'unverified' && contacts != null && (contacts.total ?? 0) > 0 ? (
            <div className="space-y-1">
              <p className="text-sm font-semibold text-emerald-700">All contacts have been email_revealed ✓</p>
              <p className="text-xs text-(--oc-muted)">Switch to "Valid" or "Campaign ready" to review results.</p>
            </div>
          ) : contacts != null && contacts.total === 0 ? (
            <div className="space-y-1">
              <p className="text-sm font-semibold text-(--oc-text)">No contacts fetched yet</p>
              <p className="text-xs text-(--oc-muted)">Reveal emails in S4 before validating them here.</p>
            </div>
          ) : (
            <p className="text-sm text-(--oc-muted)">No contacts match this filter.</p>
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
                    disabled={isLoading || isValidating}
                    ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                    onChange={() =>
                      onToggleAll(allVisibleSelected ? [] : visibleContacts.map((c) => c.id))
                    }
                    className="cursor-pointer disabled:cursor-not-allowed"
                  />
                </th>
                <SortableHeader label="Contact" field="first_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
                <SortableHeader label="Company" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
                <SortableHeader label="Modified" field="updated_at" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
                <th className="p-3 text-left font-semibold">Email</th>
                <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
                <SortableHeader label="Verification" field="verification_status" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
                <th className="p-3 text-left font-semibold">Last validated</th>
                <SortableHeader label="Stage" field="pipeline_stage" sortBy={sortBy} sortDir={sortDir} onSort={onSort} disabled={isLoading} />
              </tr>
            </thead>
            <tbody>
              {visibleContacts.map((contact) => {
                const vb = verifBadge(contact)
                const sb = stageBadge(contact)
                const fullName = [contact.first_name, contact.last_name].filter(Boolean).join(' ') || '—'
                return (
                  <tr
                    key={contact.id}
                    className="border-b border-(--oc-border) last:border-0 transition"
                    style={selectedSet.has(contact.id) ? { backgroundColor: 'var(--s5-bg)' } : {}}
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={selectedSet.has(contact.id)}
                        disabled={isLoading || isValidating}
                        onChange={() => onToggleContact(contact.id)}
                        className="cursor-pointer disabled:cursor-not-allowed"
                      />
                    </td>
                    <td className="p-3">
                      <div className="font-semibold text-sm">{fullName}</div>
                      {contact.title && (
                        <div className="text-[11px] text-(--oc-muted)">{contact.title}</div>
                      )}
                    </td>
                    <td className="p-3">
                      <a
                        href={`https://${contact.domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-[11px] font-medium hover:underline"
                        style={{ color: 'var(--s5-text)' }}
                      >
                        {contact.domain}
                      </a>
                    </td>
                    <td className="p-3 text-[11px] text-(--oc-muted) tabular-nums">
                      <RelativeTimeLabel timestamp={contact.updated_at} prefix="" />
                    </td>
                    <td className="p-3">
                      {contact.email ? (
                        <span className="font-mono text-[11.5px] text-(--oc-text)">{contact.email}</span>
                      ) : (
                        <span className="text-xs text-(--oc-muted) italic">No email</span>
                      )}
                    </td>
                    <td className="p-3">
                      {contact.title_match ? (
                        <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12"/>
                          </svg>
                          Match
                        </span>
                      ) : (
                        <span className="text-[11px] text-(--oc-muted)">No match</span>
                      )}
                    </td>
                    <td className="p-3">
                      {vb ? (
                        <span
                          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold"
                          style={{ backgroundColor: vb.bg, color: vb.text }}
                        >
                          <span
                            className="h-1.5 w-1.5 rounded-full shrink-0"
                            style={{ backgroundColor: vb.dot }}
                          />
                          {vb.label}
                        </span>
                      ) : (
                        <span className="text-[11px] text-(--oc-muted)">Unverified</span>
                      )}
                    </td>
                    <td className="p-3">
                      {(() => {
                        const validatedAt = getLastValidatedAt(contact)
                        if (!validatedAt) return <span className="text-[11px] text-(--oc-muted)">Unknown</span>
                        const stale = isStaleOver30Days(contact)
                        return (
                          <span className={`text-[11px] ${stale ? 'text-amber-700' : 'text-emerald-700'}`}>
                            {validatedAt.toLocaleDateString()} {stale ? '(stale)' : '(fresh)'}
                          </span>
                        )
                      })()}
                    </td>
                    <td className="p-3">
                      {sb ? (
                        <span
                          className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold"
                          style={{ backgroundColor: sb.bg, color: sb.text }}
                        >
                          {sb.label}
                        </span>
                      ) : (
                        <span className="text-[11px] text-(--oc-muted)">Fetched</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
