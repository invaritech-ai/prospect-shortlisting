import type { ContactCountsResponse, ContactListResponse, ProspectContactRead, S4VerifFilter } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { SortableHeader } from '../../ui/SortableHeader'
import { Pager } from '../../ui/Pager'

interface S4ValidationViewProps {
  contacts: ContactListResponse | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  verifFilter: S4VerifFilter
  selectedContactIds: string[]
  totalMatching: number | null
  contactCounts: ContactCountsResponse | null
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
]

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
  if (contact.pipeline_stage === 'verified') return { label: 'Verified', bg: '#f1f5f9', text: '#334155' }
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
  const selectedSet = new Set(selectedContactIds)

  // Server already applies verifFilter; client only applies letter filter
  const visibleContacts = (contacts?.items ?? []).filter((c) => {
    const letterOk = activeLetters.size === 0 || activeLetters.has(c.domain?.[0]?.toLowerCase() ?? '')
    return letterOk
  })

  const allVisibleSelected =
    visibleContacts.length > 0 && visibleContacts.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleContacts.some((c) => selectedSet.has(c.id))

  const displayCount = contacts?.total ?? visibleContacts.length
  const effectiveTotalMatching = totalMatching

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 space-y-2 pb-1" style={{ backgroundColor: 'var(--oc-bg)' }}>
      {/* Header */}
      <div className="flex items-center gap-2 rounded-xl px-3 py-2.5" style={{ borderLeft: '3px solid var(--s4)', backgroundColor: 'var(--s4-bg)' }}>
        <div className="flex-1">
          <h2 className="text-base font-bold" style={{ color: 'var(--s4-text)' }}>S4 · Validation</h2>
          <p className="text-xs" style={{ color: 'var(--s4-text)', opacity: 0.7 }}>
            Validate contact emails with ZeroBounce ·{' '}
            {contacts != null ? `${displayCount.toLocaleString()} contacts` : '—'}
          </p>
        </div>
        {exportUrl && (
          <a
            href={exportUrl}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium transition"
            style={{ borderColor: 'var(--s4)', color: 'var(--s4-text)' }}
          >
            Export CSV
          </a>
        )}
      </div>

      {/* Stats bar */}
      {contactCounts && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Valid', value: contactCounts.verified, color: '#15803d', bg: '#dcfce7' },
            { label: 'Eligible', value: contactCounts.eligible_verify, color: '#d97706', bg: '#fef3c7' },
            { label: 'Unverified', value: contactCounts.total - contactCounts.verified, color: '#334155', bg: '#f1f5f9' },
            { label: 'Campaign ready', value: contactCounts.campaign_ready, color: '#6b21a8', bg: '#f3e8ff' },
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

      {/* Letter strip */}
      <LetterStrip
        multiSelect
        activeLetters={activeLetters}
        counts={letterCounts}
        onToggle={onToggleLetter}
        onClear={onClearLetters}
      />

      {/* Verification filter chips + pager */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {VERIF_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => onVerifFilterChange(f.value)}
              className={`rounded-full px-3 py-1 text-[11px] font-bold transition ${
                verifFilter === f.value
                  ? 'text-white'
                  : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s4) hover:text-(--s4-text)'
              }`}
              style={
                verifFilter === f.value
                  ? { backgroundColor: f.color ?? 'var(--s4)' }
                  : {}
              }
            >
              {f.label}
            </button>
          ))}
        </div>
        <Pager offset={offset} pageSize={pageSize} total={contacts?.total ?? null} hasMore={contacts?.has_more ?? false} onPrev={onPagePrev} onNext={onPageNext} onPageSizeChange={onPageSizeChange} />
      </div>

      {/* Selection bar */}
      <SelectionBar
        stageColor="--s4"
        stageBg="--s4-bg"
        selectedCount={selectedContactIds.length}
        totalMatching={effectiveTotalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedContactIds.length > 0 ? onSelectAllMatching : null}
        isSelectingAll={isSelectingAll}
        onClear={onClearSelection}
      >
        <button
          type="button"
          onClick={onValidateSelected}
          disabled={isValidating || selectedContactIds.length === 0}
          className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
          style={{ backgroundColor: 'var(--s4)' }}
        >
          {isValidating ? 'Queuing…' : 'Validate with ZeroBounce'}
        </button>
      </SelectionBar>
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
              <p className="text-sm font-semibold text-emerald-700">All contacts have been verified ✓</p>
              <p className="text-xs text-(--oc-muted)">Switch to "Valid" or "Campaign ready" to review results.</p>
            </div>
          ) : contacts != null && contacts.total === 0 ? (
            <div className="space-y-1">
              <p className="text-sm font-semibold text-(--oc-text)">No contacts fetched yet</p>
              <p className="text-xs text-(--oc-muted)">Go to S3 to fetch contacts for classified companies.</p>
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
                    ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                    onChange={() =>
                      onToggleAll(allVisibleSelected ? [] : visibleContacts.map((c) => c.id))
                    }
                    className="cursor-pointer"
                  />
                </th>
                <SortableHeader label="Contact" field="first_name" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortableHeader label="Company" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <th className="p-3 text-left font-semibold">Email</th>
                <th className="p-3 text-left font-semibold">Source</th>
                <SortableHeader label="Title" field="title" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortableHeader label="Verification" field="verification_status" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
                <SortableHeader label="Stage" field="pipeline_stage" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
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
                    style={selectedSet.has(contact.id) ? { backgroundColor: 'var(--s4-bg)' } : {}}
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={selectedSet.has(contact.id)}
                        onChange={() => onToggleContact(contact.id)}
                        className="cursor-pointer"
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
                        style={{ color: 'var(--s4-text)' }}
                      >
                        {contact.domain}
                      </a>
                    </td>
                    <td className="p-3">
                      {contact.email ? (
                        <span className="font-mono text-[11.5px] text-(--oc-text)">{contact.email}</span>
                      ) : (
                        <span className="text-xs text-(--oc-muted) italic">No email</span>
                      )}
                    </td>
                    <td className="p-3">
                      <span className="inline-flex items-center rounded-md border border-(--oc-border) bg-(--oc-surface) px-1.5 py-0.5 text-[10px] font-bold text-(--oc-muted)">
                        {contact.source}
                      </span>
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
