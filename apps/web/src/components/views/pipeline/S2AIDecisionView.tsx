import { useRef, useState } from 'react'
import type { CompanyList, CompanyListItem, PromptRead, RunRead, StatsResponse } from '../../../lib/types'
import { LetterStrip } from '../../ui/LetterStrip'
import { SelectionBar } from '../../ui/SelectionBar'
import { Badge } from '../../ui/Badge'
import { decisionBgClass } from '../../ui/badgeUtils'
import { SortableHeader } from '../../ui/SortableHeader'

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
  stats: StatsResponse | null
  onToggleLetter: (l: string) => void
  onClearLetters: () => void
  onToggleRow: (id: string) => void
  onToggleAll: (visibleIds: string[]) => void
  onSelectAllMatching: () => void
  onClearSelection: () => void
  onAnalyzeSelected: () => void
  onClassifyOne: (company: CompanyListItem) => void
  onReviewCompany: (company: CompanyListItem) => void
  onViewMarkdown: (company: CompanyListItem) => void
  onOpenPromptLibrary: () => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
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
  stats,
  onToggleLetter,
  onClearLetters,
  onToggleRow,
  onToggleAll,
  onSelectAllMatching,
  onClearSelection,
  onAnalyzeSelected,
  onClassifyOne,
  onReviewCompany,
  onViewMarkdown,
  onOpenPromptLibrary,
  sortBy,
  sortDir,
  onSort,
}: S2AIDecisionViewProps) {
  const [decisionSub, setDecisionSub] = useState<DecisionSubFilter>('all')
  const [search, setSearch] = useState('')
  const [dropOpen, setDropOpen] = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)
  const selectedSet = new Set(selectedIds)

  const visibleCompanies = (companies?.items ?? []).filter((c) => {
    if (search && !c.domain.toLowerCase().includes(search.toLowerCase())) return false
    const letterOk = activeLetters.size === 0 || activeLetters.has(c.domain[0].toLowerCase())
    if (!letterOk) return false
    const decision = (c.feedback_manual_label ?? c.latest_decision ?? '').toLowerCase()
    if (decisionSub === 'unlabeled') return !decision
    if (decisionSub === 'possible') return decision === 'possible'
    if (decisionSub === 'unknown') return decision === 'unknown'
    if (decisionSub === 'crap') return decision === 'crap'
    return true
  })

  const allVisibleSelected =
    visibleCompanies.length > 0 && visibleCompanies.every((c) => selectedSet.has(c.id))
  const someVisibleSelected =
    !allVisibleSelected && visibleCompanies.some((c) => selectedSet.has(c.id))

  const isSubFiltered = decisionSub !== 'all' || search !== ''
  const displayCount = isSubFiltered ? visibleCompanies.length : (companies?.total ?? 0)
  const effectiveTotalMatching = isSubFiltered ? visibleCompanies.length : totalMatching

  // Analysis pipeline progress
  const analysis = stats?.analysis
  const aRunning = analysis?.running ?? 0
  const aQueued = analysis?.queued ?? 0
  const aCompleted = analysis?.completed ?? 0
  const aFailed = analysis?.failed ?? 0
  const aTotal = analysis?.total ?? 0
  const aPct = analysis?.pct_done ?? 0
  const aHasActivity = aRunning > 0 || aQueued > 0

  return (
    <div className="space-y-3">
      {/* Analysis pipeline progress */}
      {analysis && (aHasActivity || aCompleted > 0) && (
        <div className="rounded-2xl border border-(--oc-border) bg-white p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-(--oc-muted)">
                Analysis Pipeline
              </span>
              {aHasActivity && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                  Active
                </span>
              )}
            </div>
            <span className="text-[11px] text-(--oc-muted)">{aCompleted.toLocaleString()} / {aTotal.toLocaleString()}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-(--oc-surface)" style={{ border: '1px solid var(--oc-border)' }}>
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(aPct, 100)}%`,
                background: aHasActivity ? 'linear-gradient(90deg, var(--s2), #f59e0b)' : '#16a34a',
              }}
            />
          </div>
          <div className="mt-2.5 flex gap-5 text-[11px]">
            {aRunning > 0 && <span className="font-bold text-amber-600">{aRunning.toLocaleString()} <span className="font-normal text-(--oc-muted)">running</span></span>}
            {aQueued > 0 && <span className="font-bold text-(--oc-muted)">{aQueued.toLocaleString()} <span className="font-normal">queued</span></span>}
            <span className="font-bold text-emerald-700">{aCompleted.toLocaleString()} <span className="font-normal text-(--oc-muted)">done</span></span>
            {aFailed > 0 && <span className="font-bold text-rose-600">{aFailed.toLocaleString()} <span className="font-normal text-(--oc-muted)">failed</span></span>}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <div className="flex-1">
          <h2 className="text-base font-bold" style={{ color: 'var(--s2-text)' }}>S2 · AI Decision</h2>
          <p className="text-xs text-(--oc-muted)">
            Qualify prospects with AI classification · {companies != null ? `${displayCount.toLocaleString()} companies` : '—'}
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
            className="rounded-lg border border-(--oc-border) bg-(--oc-surface) py-1.5 pl-7 pr-3 text-xs outline-none transition focus:border-(--s2) focus:bg-white"
            style={{ width: 180 }}
          />
        </div>
        <button
          type="button"
          onClick={onOpenPromptLibrary}
          className="text-xs text-(--oc-muted) underline underline-offset-2 hover:text-(--oc-text) transition whitespace-nowrap"
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
        totalMatching={effectiveTotalMatching}
        activeLetters={activeLetters}
        onSelectAllMatching={selectedIds.length > 0 && !isSubFiltered ? onSelectAllMatching : null}
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
              <SortableHeader label="Domain" field="domain" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Decision" field="decision" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Confidence" field="confidence" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
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
                <td className="p-3">
                  <a
                    href={c.normalized_url || c.raw_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[12px] font-medium hover:underline"
                    style={{ color: 'var(--s2)' }}
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
                    {c.latest_scrape_job_id && (
                      <button
                        type="button"
                        onClick={() => onViewMarkdown(c)}
                        className="rounded-lg border border-(--oc-border) px-2 py-1 text-[11px] font-medium transition hover:border-(--s2) hover:text-(--s2-text)"
                      >
                        Markdown
                      </button>
                    )}
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
