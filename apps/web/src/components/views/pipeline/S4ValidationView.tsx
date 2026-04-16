import type { ContactCompanyListResponse, ContactCountsResponse } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'

interface S4ValidationViewProps {
  companies: ContactCompanyListResponse | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  selectedCompanyIds: string[]
  totalMatching: number | null
  contactCounts: ContactCountsResponse | null
  isLoading: boolean
  isValidating: boolean
  isSelectingAll: boolean
  exportUrl: string
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleCompany: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onValidateSelected: () => void
}

export function S4ValidationView({
  companies,
  letterCounts,
  activeLetters,
  selectedCompanyIds,
  totalMatching,
  contactCounts,
  isLoading,
  isValidating,
  isSelectingAll,
  exportUrl,
  onToggleLetter,
  onClearLetters,
  onToggleCompany,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onValidateSelected,
}: S4ValidationViewProps) {
  const selectedSet = new Set(selectedCompanyIds)

  const visibleCompanies = (companies?.items ?? []).filter(
    (c) => activeLetters.size === 0 || activeLetters.has(c.domain[0].toLowerCase()),
  )

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.company_id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.company_id))

  const totalEligible = visibleCompanies
    .filter((c) => selectedSet.has(c.company_id))
    .reduce((sum, c) => sum + c.eligible_verify_count, 0)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold" style={{ color: 'var(--s4-text)' }}>S4 · Validation</h2>
          <p className="text-xs text-(--oc-muted)">
            Validate contact emails with ZeroBounce ·{' '}
            {contactCounts != null
              ? `${contactCounts.total.toLocaleString()} contacts`
              : '—'}
          </p>
        </div>
        {exportUrl && (
          <a
            href={exportUrl}
            className="rounded-lg border border-(--oc-border) px-3 py-1.5 text-xs font-medium transition hover:border-(--oc-accent) hover:text-(--oc-accent)"
          >
            Export CSV
          </a>
        )}
      </div>

      {/* Stats strip */}
      {contactCounts && (
        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Total', value: contactCounts.total, color: 'var(--s4)' },
            { label: 'Verified', value: contactCounts.verified, color: '#15803d' },
            { label: 'Campaign ready', value: contactCounts.campaign_ready, color: '#0369a1' },
            { label: 'Eligible to verify', value: contactCounts.eligible_verify, color: '#92400e' },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs"
              style={{ borderColor: color + '44', backgroundColor: color + '11' }}
            >
              <span className="font-black tabular-nums" style={{ color }}>{value.toLocaleString()}</span>
              <span style={{ color: color + 'aa' }}>{label}</span>
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

      <SelectionBar
        stageColor="--s4"
        stageBg="--s4-bg"
        selectedCount={selectedCompanyIds.length}
        totalMatching={totalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedCompanyIds.length > 0 ? onSelectAllMatching : null}
        isSelectingAll={isSelectingAll}
        onClear={onClearSelection}
      >
        <span className="text-xs" style={{ color: 'var(--s4-text)' }}>
          {totalEligible > 0 && `${totalEligible.toLocaleString()} eligible`}
        </span>
        <button
          type="button"
          onClick={onValidateSelected}
          disabled={isValidating || selectedCompanyIds.length === 0}
          className="rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
          style={{ backgroundColor: 'var(--s4)' }}
        >
          {isValidating ? 'Queuing…' : 'Validate with ZeroBounce'}
        </button>
      </SelectionBar>

      {isLoading && (
        <p className="p-6 text-center text-sm text-(--oc-muted)">Loading contacts…</p>
      )}

      {!isLoading && visibleCompanies.length === 0 && (
        <p className="p-6 text-center text-sm text-(--oc-muted)">No companies with contacts found.</p>
      )}

      {!isLoading && visibleCompanies.length > 0 && (
        <div className="oc-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-(--oc-border) text-xs text-(--oc-muted)">
                <th className="w-8 p-3">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    ref={(el) => { if (el) el.indeterminate = someVisibleSelected }}
                    onChange={() =>
                      onToggleAll(allVisibleSelected ? [] : visibleCompanies.map((c) => c.company_id))
                    }
                    className="cursor-pointer"
                  />
                </th>
                <th className="p-3 text-left font-semibold">Domain</th>
                <th className="p-3 text-left font-semibold">Total</th>
                <th className="p-3 text-left font-semibold">Title matched</th>
                <th className="p-3 text-left font-semibold">Verified</th>
                <th className="p-3 text-left font-semibold">Eligible</th>
                <th className="p-3 text-left font-semibold">Campaign ready</th>
              </tr>
            </thead>
            <tbody>
              {visibleCompanies.map((c) => (
                <tr
                  key={c.company_id}
                  className="border-b border-(--oc-border) last:border-0 transition"
                  style={selectedSet.has(c.company_id) ? { backgroundColor: 'var(--s4-bg)' } : {}}
                >
                  <td className="p-3">
                    <input
                      type="checkbox"
                      checked={selectedSet.has(c.company_id)}
                      onChange={() => onToggleCompany(c.company_id)}
                      className="cursor-pointer"
                    />
                  </td>
                  <td className="p-3 font-medium" style={{ color: 'var(--s4-text)' }}>{c.domain}</td>
                  <td className="p-3 text-xs font-mono text-(--oc-muted)">{c.total_count}</td>
                  <td className="p-3 text-xs font-mono">
                    {c.title_matched_count > 0 ? (
                      <span className="font-semibold text-emerald-700">{c.title_matched_count}</span>
                    ) : (
                      <span className="text-(--oc-border)">0</span>
                    )}
                  </td>
                  <td className="p-3 text-xs font-mono">
                    {c.verified_count > 0 ? (
                      <span className="font-semibold text-emerald-700">{c.verified_count}</span>
                    ) : (
                      <span className="text-(--oc-border)">0</span>
                    )}
                  </td>
                  <td className="p-3 text-xs font-mono">
                    {c.eligible_verify_count > 0 ? (
                      <span className="font-semibold" style={{ color: 'var(--s4)' }}>{c.eligible_verify_count}</span>
                    ) : (
                      <span className="text-(--oc-border)">0</span>
                    )}
                  </td>
                  <td className="p-3 text-xs font-mono">
                    {c.campaign_ready_count > 0 ? (
                      <span className="font-semibold text-blue-700">{c.campaign_ready_count}</span>
                    ) : (
                      <span className="text-(--oc-border)">0</span>
                    )}
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
