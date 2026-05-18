import { useState, useMemo } from 'react'
import { MOCK_AI_ROWS, MOCK_AI_STATS, MOCK_STATS } from '../../../lib/useAppData'
import type { AIVerdict, MockAIRow } from '../../../lib/useAppData'
import type { StatsResponse } from '../../../lib/types'
import { StageViewHeader }    from '../shared/StageViewHeader'
import { AIReviewToolbar }    from './AIReviewToolbar'
import { AIReviewTable }      from './AIReviewTable'
import { AIReviewCards }      from './AIReviewCards'
import { AIReasoningDrawer }  from './AIReasoningDrawer'
import { AISettingsDrawer }   from './AISettingsDrawer'

type VerdictFilter = 'all' | AIVerdict

interface AIReviewViewProps {
  stats?: StatsResponse | null
}

export function AIReviewView({ stats: rawStats }: AIReviewViewProps) {
  const stats = rawStats ?? MOCK_STATS

  const [rows, setRows]             = useState<MockAIRow[]>(MOCK_AI_ROWS)
  const [filter, setFilter]         = useState<VerdictFilter>('all')
  const [search, setSearch]         = useState('')
  const [selected, setSelected]     = useState<Set<string>>(new Set())
  const [reasoningRow, setReasoningRow] = useState<MockAIRow | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const aiStats = [
    { label: 'possible', value: rows.filter((r) => r.verdict === 'Possible').length, color: 'var(--s2)', live: (stats.analysis?.running ?? 0) > 0 },
    { label: 'unknown',  value: rows.filter((r) => r.verdict === 'Unknown').length,  color: 'var(--oc-warn-text)' },
    { label: 'crap',     value: rows.filter((r) => r.verdict === 'Crap').length,     color: 'var(--oc-fail-text)' },
    { label: 'queued',   value: stats.analysis?.queued ?? MOCK_AI_STATS.running },
  ]

  const filtered = useMemo(() => {
    let list = rows
    if (filter !== 'all') list = list.filter((r) => r.verdict === filter)
    if (search.trim())    list = list.filter((r) => r.domain.toLowerCase().includes(search.toLowerCase().trim()))
    return list
  }, [rows, filter, search])

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (filtered.every((r) => selected.has(r.id))) {
      setSelected(new Set())
    } else {
      setSelected(new Set(filtered.map((r) => r.id)))
    }
  }

  function handleLabelChange(id: string, verdict: AIVerdict) {
    setRows((prev) => prev.map((r) => r.id === id ? { ...r, verdict } : r))
  }

  function handleBulkLabel(verdict: AIVerdict) {
    const ids = [...selected]
    setRows((prev) => prev.map((r) => ids.includes(r.id) ? { ...r, verdict } : r))
    setSelected(new Set())
  }

  const unknownCount = rows.filter((r) => r.verdict === 'Unknown').length
  const etaSecs = stats.analysis?.eta_seconds ?? null

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <StageViewHeader
          stageNum="S2"
          stageLabel="AI Review"
          stageColor="var(--s2)"
          stageBg="var(--s2-bg)"
          stats={aiStats}
          etaSeconds={etaSecs}
          onOpenSettings={() => setSettingsOpen(true)}
          settingsLabel="Prompt"
          primaryAction={unknownCount > 0 ? {
            label: `Review ${unknownCount} unknown`,
            onClick: () => setFilter('Unknown'),
          } : {
            label: 'Classify unreviewed',
            onClick: () => console.log('Classify all'),
          }}
          secondaryAction={rows.filter((r) => r.verdict === 'Possible').length > 0 ? {
            label: `${rows.filter((r) => r.verdict === 'Possible').length} possible →`,
            onClick: () => setFilter('Possible'),
          } : undefined}
        />

        <AIReviewToolbar
          rows={rows}
          filter={filter}
          search={search}
          selectedIds={selected}
          onFilterChange={setFilter}
          onSearchChange={setSearch}
          onClassifyAll={() => console.log('Classify all')}
          onBulkLabel={handleBulkLabel}
          onClearSelection={() => setSelected(new Set())}
        />

        {filtered.length === 0 ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            No companies match this filter.
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <AIReviewTable
                rows={filtered}
                selectedIds={selected}
                onToggleRow={toggleSelect}
                onToggleAll={toggleSelectAll}
                onLabelChange={handleLabelChange}
                onViewReasoning={setReasoningRow}
              />
            </div>
            <div className="md:hidden">
              <AIReviewCards
                rows={filtered}
                selectedIds={selected}
                onToggleRow={toggleSelect}
                onLabelChange={handleLabelChange}
                onViewReasoning={setReasoningRow}
              />
            </div>
          </>
        )}

      </div>

      <AIReasoningDrawer row={reasoningRow} onClose={() => setReasoningRow(null)} />
      <AISettingsDrawer isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  )
}
