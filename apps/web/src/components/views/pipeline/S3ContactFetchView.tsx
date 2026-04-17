import type { CompanyList, CompanyListItem } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { decisionBgClass } from '../../ui/badgeUtils'

interface S3ContactFetchViewProps {
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  selectedIds: string[]
  totalMatching: number | null
  isLoading: boolean
  isFetching: boolean
  isSelectingAll: boolean
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onFetchOne: (company: CompanyListItem, source: 'snov' | 'apollo') => void
  onFetchSelected: (source: 'snov' | 'apollo' | 'both') => void
  onOpenTitleRules: () => void
}

const FETCH_BUTTONS: Array<{ source: 'apollo' | 'snov' | 'both'; label: string; bg: string }> = [
  { source: 'apollo', label: 'Fetch · Apollo', bg: '#15803d' },
  { source: 'snov', label: 'Fetch · Snov.io', bg: '#0369a1' },
  { source: 'both', label: 'Fetch · Both', bg: '#1e40af' },
]

export function S3ContactFetchView({
  companies,
  letterCounts,
  activeLetters,
  selectedIds,
  totalMatching,
  isLoading,
  isFetching,
  isSelectingAll,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onFetchOne,
  onFetchSelected,
  onOpenTitleRules,
}: S3ContactFetchViewProps) {
  const selectedSet = new Set(selectedIds)

  const visibleCompanies = (companies?.items ?? []).filter(
    (c) => activeLetters.size === 0 || activeLetters.has(c.domain[0].toLowerCase()),
  )

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold" style={{ color: 'var(--s3-text)' }}>S3 · Contact Fetch</h2>
          <p className="text-xs text-(--oc-muted)">
            Find contacts at qualified companies · {companies?.total != null ? `${companies.total.toLocaleString()} companies` : '—'}
          </p>
        </div>
        <button
          type="button"
          onClick={onOpenTitleRules}
          className="rounded-lg border border-(--oc-border) px-3 py-1.5 text-xs font-medium transition hover:border-(--s3) hover:text-(--s3-text)"
        >
          Title Rules
        </button>
      </div>

      <LetterStrip
        multiSelect
        activeLetters={activeLetters}
        counts={letterCounts}
        onToggle={onToggleLetter}
        onClear={onClearLetters}
      />

      <SelectionBar
        stageColor="--s3"
        stageBg="--s3-bg"
        selectedCount={selectedIds.length}
        totalMatching={totalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
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
              <th className="p-3 text-left font-semibold">Domain</th>
              <th className="p-3 text-left font-semibold">Decision</th>
              <th className="p-3 text-left font-semibold">Contacts</th>
              <th className="p-3 text-left font-semibold">Fetch</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="p-6 text-center text-(--oc-muted)">Loading…</td></tr>
            )}
            {!isLoading && visibleCompanies.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-(--oc-muted)">No companies at this stage.</td></tr>
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
                <td className="p-3 font-medium">{c.domain}</td>
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
                      onClick={() => onFetchOne(c, 'snov')}
                      className="rounded border border-(--oc-border) px-1.5 py-0.5 text-[10px] transition hover:border-(--s3)"
                    >
                      Snov
                    </button>
                    <button
                      type="button"
                      onClick={() => onFetchOne(c, 'apollo')}
                      className="rounded border border-(--oc-border) px-1.5 py-0.5 text-[10px] transition hover:border-(--s3)"
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
