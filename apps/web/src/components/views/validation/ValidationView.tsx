import { useState, useMemo } from 'react'
import { MOCK_VALIDATION_ROWS, MOCK_VALIDATION_STATS, MOCK_STATS } from '../../../lib/useAppData'
import type { ValidationStatus } from '../../../lib/useAppData'
import type { StatsResponse } from '../../../lib/types'
import { StageViewHeader }            from '../shared/StageViewHeader'
import { StageToolbar }               from '../shared/StageToolbar'
import { ValidationTable }            from './ValidationTable'
import { ValidationCards }            from './ValidationCards'
import { ValidationSettingsDrawer }   from './ValidationSettingsDrawer'

type FilterValue = 'all' | ValidationStatus

const FILTERS = [
  { value: 'all',     label: 'All' },
  { value: 'valid',   label: 'Deliverable', color: 'var(--oc-success-text)' },
  { value: 'risky',   label: 'Risky',       color: 'var(--oc-warn-text)' },
  { value: 'invalid', label: 'Invalid',     color: 'var(--oc-fail-text)' },
  { value: 'unknown', label: 'Unknown',     color: 'var(--oc-muted)' },
  { value: 'pending', label: 'Pending' },
]

interface ValidationViewProps {
  stats?: StatsResponse | null
}

export function ValidationView({ stats: rawStats }: ValidationViewProps) {
  const stats = rawStats ?? MOCK_STATS

  const [rows, setRows]           = useState(MOCK_VALIDATION_ROWS)
  const [filter, setFilter]       = useState<FilterValue>('all')
  const [search, setSearch]       = useState('')
  const [selected, setSelected]   = useState<Set<string>>(new Set())
  const [settingsOpen, setSettingsOpen] = useState(false)

  const validationStats = [
    { label: 'deliverable', value: rows.filter((r) => r.status === 'valid').length,   color: 'var(--oc-success-text)' },
    { label: 'risky',       value: rows.filter((r) => r.status === 'risky').length,   color: 'var(--oc-warn-text)' },
    { label: 'invalid',     value: rows.filter((r) => r.status === 'invalid').length, color: 'var(--oc-fail-text)' },
    { label: 'checking',    value: MOCK_VALIDATION_STATS.running, color: 'var(--s5)', live: MOCK_VALIDATION_STATS.running > 0 },
    { label: 'queued',      value: stats.validation?.queued ?? MOCK_VALIDATION_STATS.pending },
  ]

  const filtered = useMemo(() => {
    let list = rows
    if (filter !== 'all') list = list.filter((r) => r.status === filter)
    if (search.trim())    list = list.filter((r) =>
      r.email.toLowerCase().includes(search.toLowerCase()) ||
      r.contactName.toLowerCase().includes(search.toLowerCase()) ||
      r.domain.toLowerCase().includes(search.toLowerCase())
    )
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

  function handleValidate(id: string) {
    setRows((prev) => prev.map((r) => r.id === id ? { ...r, status: 'running' as ValidationStatus } : r))
    // Simulate completion after 2s
    setTimeout(() => {
      setRows((prev) => prev.map((r) => r.id === id ? { ...r, status: 'valid' as ValidationStatus, score: 9, updatedAt: new Date().toISOString() } : r))
    }, 2000)
  }

  const pendingCount = MOCK_VALIDATION_STATS.pending
  const etaSecs = stats.validation?.eta_seconds ?? null

  const bulkActions = [
    { label: `Validate ${selected.size} emails`, onClick: () => { [...selected].forEach(handleValidate); setSelected(new Set()) } },
  ]

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <StageViewHeader
          stageNum="S4"
          stageLabel="Validation"
          stageColor="var(--s5)"
          stageBg="var(--s5-bg)"
          stats={validationStats}
          etaSeconds={etaSecs}
          onOpenSettings={() => setSettingsOpen(true)}
          settingsLabel="ZeroBounce"
          primaryAction={pendingCount > 0 ? {
            label: `Validate ${pendingCount} pending`,
            onClick: () => console.log('Validate all pending'),
          } : undefined}
          secondaryAction={rows.filter((r) => r.status === 'unknown').length > 0 ? {
            label: `${rows.filter((r) => r.status === 'unknown').length} unknown`,
            onClick: () => setFilter('unknown'),
          } : undefined}
        />

        <StageToolbar
          stageColor="var(--s5)"
          filters={FILTERS}
          activeFilter={filter}
          onFilterChange={(v) => setFilter(v as FilterValue)}
          search={search}
          onSearchChange={setSearch}
          selectedCount={selected.size}
          bulkActions={selected.size > 0 ? bulkActions : []}
          onClearSelection={() => setSelected(new Set())}
        />

        {filtered.length === 0 ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            No emails match this filter.
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <ValidationTable
                rows={filtered}
                selected={selected}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                onValidate={handleValidate}
              />
            </div>
            <div className="md:hidden">
              <ValidationCards
                rows={filtered}
                selected={selected}
                onToggleSelect={toggleSelect}
                onValidate={handleValidate}
              />
            </div>
          </>
        )}

      </div>

      <ValidationSettingsDrawer isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  )
}
