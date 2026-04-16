import { useRef, useState } from 'react'
import type { CompanyList, CompanyListItem, PromptRead, RunRead } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { decisionBgClass } from '../../ui/badgeUtils'

type DecisionSubFilter = 'all' | 'unlabeled' | 'possible' | 'unknown' | 'crap'

interface S2AIDecisionViewProps {
  companies: CompanyList | null
  letterCounts: Record<string, number>
  activeLetters: Set<string>
  selectedIds: string[]
  totalMatching: number | null
  isLoading: boolean
  isAnalyzing: boolean
  isSelectingAll: boolean
  prompts: PromptRead[]
  selectedPrompt: PromptRead | null
  recentRuns: RunRead[]
  analysisActionState: Record<string, string>
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onAnalyzeSelected: () => void
  onClassifyOne: (company: CompanyListItem) => void
  onReviewCompany: (company: CompanyListItem) => void
  onOpenPromptLibrary: () => void
}

const DECISION_FILTERS: Array<{ value: DecisionSubFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'unlabeled', label: 'Unlabeled' },
  { value: 'possible', label: 'Possible' },
  { value: 'unknown', label: 'Unknown' },
  { value: 'crap', label: 'Crap' },
]

export function S2AIDecisionView({
  companies,
  letterCounts,
  activeLetters,
  selectedIds,
  totalMatching,
  isLoading,
  isAnalyzing,
  isSelectingAll,
  prompts,
  selectedPrompt,
  recentRuns,
  analysisActionState,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onAnalyzeSelected,
  onClassifyOne,
  onReviewCompany,
  onOpenPromptLibrary,
}: S2AIDecisionViewProps) {
  const [decisionSub, setDecisionSub] = useState<DecisionSubFilter>('all')
  const [dropOpen, setDropOpen] = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)
  const selectedSet = new Set(selectedIds)

  const visibleCompanies = (companies?.items ?? []).filter((c) => {
    const letterOk = activeLetters.size === 0 || activeLetters.has(c.domain[0].toLowerCase())
    if (!letterOk) return false
    if (decisionSub === 'unlabeled') return !c.latest_decision && !c.feedback_manual_label
    if (decisionSub === 'possible') return c.latest_decision === 'Possible' || c.latest_decision === 'possible' || c.feedback_manual_label === 'possible'
    if (decisionSub === 'unknown') return c.latest_decision === 'Unknown' || c.latest_decision === 'unknown'
    if (decisionSub === 'crap') return c.latest_decision === 'Crap' || c.latest_decision === 'crap'
    return true
  })

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold" style={{ color: 'var(--s2-text)' }}>S2 · AI Decision</h2>
          <p className="text-xs text-(--oc-muted)">
            Qualify prospects with AI classification · {companies?.total != null ? `${companies.total.toLocaleString()} companies` : '—'}
          </p>
        </div>
        <button
          type="button"
          onClick={onOpenPromptLibrary}
          className="text-xs text-(--oc-muted) underline underline-offset-2 hover:text-(--oc-text) transition"
        >
          {selectedPrompt ? `Prompt: ${selectedPrompt.name}` : 'Select prompt…'}
        </button>
      </div>

      <LetterStrip
        multiSelect
        activeLetters={activeLetters}
        counts={letterCounts}
        onToggle={onToggleLetter}
        onClear={onClearLetters}
      />

      <div className="flex flex-wrap gap-1.5">
        {DECISION_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => setDecisionSub(f.value)}
            className={`rounded-full px-3 py-1 text-[11px] font-bold transition ${
              decisionSub === f.value
                ? 'text-white'
                : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--s2) hover:text-(--s2-text)'
            }`}
            style={decisionSub === f.value ? { backgroundColor: 'var(--s2)' } : {}}
          >
            {f.label}
          </button>
        ))}
      </div>

      <SelectionBar
        stageColor="--s2"
        stageBg="--s2-bg"
        selectedCount={selectedIds.length}
        totalMatching={totalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedIds.length > 0 ? onSelectAllMatching : null}
        isSelectingAll={isSelectingAll}
        onClear={onClearSelection}
      >
        <div ref={dropRef} className="relative">
          <button
            type="button"
            onClick={() => setDropOpen((v) => !v)}
            disabled={isAnalyzing || selectedIds.length === 0 || !selectedPrompt?.enabled}
            className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-60"
            style={{ backgroundColor: 'var(--s2)' }}
            title={!selectedPrompt?.enabled ? 'Select an enabled prompt first' : undefined}
          >
            {isAnalyzing ? 'Queuing…' : 'Run Analysis'} <span className="text-[10px]">▾</span>
          </button>
          {dropOpen && (
            <div
              className="absolute right-0 top-full z-20 mt-1 w-56 rounded-xl border border-(--oc-border) bg-white py-1 shadow-lg"
              onMouseLeave={() => setDropOpen(false)}
            >
              <p className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide text-(--oc-muted)">Prompt</p>
              {prompts.filter((p) => p.enabled).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => { setDropOpen(false); onAnalyzeSelected() }}
                  className={`w-full px-3 py-2 text-left text-xs transition hover:bg-(--oc-surface) ${
                    p.id === selectedPrompt?.id ? 'font-bold text-(--oc-accent)' : 'text-(--oc-text)'
                  }`}
                >
                  {p.name}
                </button>
              ))}
              {prompts.filter((p) => p.enabled).length === 0 && (
                <p className="px-3 py-2 text-xs text-(--oc-muted)">No enabled prompts.</p>
              )}
            </div>
          )}
        </div>
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
                  onChange={() =>
                    onToggleAll(allVisibleSelected ? [] : visibleCompanies.map((c) => c.id))
                  }
                  className="cursor-pointer"
                />
              </th>
              <th className="p-3 text-left font-semibold">Domain</th>
              <th className="p-3 text-left font-semibold">Decision</th>
              <th className="p-3 text-left font-semibold">Confidence</th>
              <th className="p-3 text-left font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="p-6 text-center text-(--oc-muted)">Loading…</td></tr>
            )}
            {!isLoading && visibleCompanies.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-(--oc-muted)">No companies match this filter.</td></tr>
            )}
            {visibleCompanies.map((c) => (
              <tr
                key={c.id}
                className="border-b border-(--oc-border) last:border-0 transition"
                style={selectedSet.has(c.id) ? { backgroundColor: 'var(--s2-bg)' } : {}}
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
                <td className="p-3 text-xs text-(--oc-muted)">
                  {c.latest_confidence != null ? `${Math.round(c.latest_confidence * 100)}%` : '—'}
                </td>
                <td className="p-3">
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => onClassifyOne(c)}
                      disabled={!!analysisActionState[c.id]}
                      className="rounded-lg border border-(--oc-border) px-2 py-1 text-[11px] font-medium transition hover:border-(--s2) hover:text-(--s2-text) disabled:opacity-50"
                    >
                      {analysisActionState[c.id] ?? 'Classify'}
                    </button>
                    <button
                      type="button"
                      onClick={() => onReviewCompany(c)}
                      className="rounded-lg border border-(--oc-border) px-2 py-1 text-[11px] font-medium transition hover:border-(--s2) hover:text-(--s2-text)"
                    >
                      Review
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Recent runs mini-list */}
      {recentRuns.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-wide text-(--oc-muted)">Recent runs</p>
          {recentRuns.slice(0, 5).map((run) => (
            <div key={run.id} className="flex items-center gap-2 rounded-lg bg-(--oc-surface) px-3 py-2 text-xs">
              <span className="flex-1 truncate text-(--oc-muted)">{run.prompt_name ?? run.id.slice(0, 8)}</span>
              <span className="text-(--oc-muted)">{run.completed_jobs}/{run.total_jobs}</span>
              <span className="text-(--oc-muted)">{run.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
