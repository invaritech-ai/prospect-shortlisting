import { useState, useMemo } from 'react'
import { MOCK_SCRAPE_ROWS, MOCK_SCRAPE_STATS, MOCK_STATS } from '../../../lib/mockData'
import type { MockScrapeRow } from '../../../lib/mockData'
import type { StatsResponse } from '../../../lib/types'
import { StageViewHeader } from '../shared/StageViewHeader'
import { ScrapingToolbar } from './ScrapingToolbar'
import { ScrapingTable }   from './ScrapingTable'
import { ScrapingCards }   from './ScrapingCards'
import type { FilterValue } from './ScrapingToolbar'

interface ScrapingViewProps {
  stats?: StatsResponse | null
  onViewDiagnostics?: (row: MockScrapeRow) => void
}

export function ScrapingView({ stats: rawStats, onViewDiagnostics }: ScrapingViewProps) {
  const stats = rawStats ?? MOCK_STATS

  const [filter, setFilter]   = useState<FilterValue>('all')
  const [search, setSearch]   = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const scrapeStats = [
    { label: 'pending', value: MOCK_SCRAPE_STATS.pending },
    { label: 'running', value: MOCK_SCRAPE_STATS.running, live: true, color: 'var(--s1)' },
    { label: 'done',    value: MOCK_SCRAPE_STATS.done,    color: 'var(--oc-success-text)' },
    { label: 'failed',  value: MOCK_SCRAPE_STATS.failed,  color: 'var(--oc-fail-text)' },
  ]

  const filtered = useMemo(() => {
    let rows = MOCK_SCRAPE_ROWS
    if (filter !== 'all')    rows = rows.filter((r) => r.status === filter)
    if (search.trim())       rows = rows.filter((r) => r.domain.toLowerCase().includes(search.toLowerCase()))
    return rows
  }, [filter, search])

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

  function handleRetry(id: string) {
    // TODO: wire to real API
    console.log('Retry scrape:', id)
  }

  function handleScrapeAll() {
    // TODO: wire to real API
    console.log('Scrape all pending')
  }

  function handleScrapeSelected() {
    // TODO: wire to real API
    console.log('Scrape selected:', [...selected])
    setSelected(new Set())
  }

  function handleViewDiagnostics(row: MockScrapeRow) {
    onViewDiagnostics?.(row)
  }

  const hasFailed  = MOCK_SCRAPE_STATS.failed > 0
  const hasPending = MOCK_SCRAPE_STATS.pending > 0
  const etaSecs    = stats.scrape.eta_seconds ?? null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

      <StageViewHeader
        stageNum="S1"
        stageLabel="Scraping"
        stageColor="var(--s1)"
        stageBg="var(--s1-bg)"
        stats={scrapeStats}
        etaSeconds={etaSecs}
        primaryAction={hasPending ? {
          label: `Scrape ${MOCK_SCRAPE_STATS.pending.toLocaleString()} pending`,
          onClick: handleScrapeAll,
        } : undefined}
        secondaryAction={hasFailed ? {
          label: `Retry ${MOCK_SCRAPE_STATS.failed} failed`,
          onClick: () => setFilter('failed'),
        } : undefined}
      />

      <ScrapingToolbar
        filter={filter}
        search={search}
        onFilterChange={setFilter}
        onSearchChange={setSearch}
        selectedCount={selected.size}
        onScrapeSelected={handleScrapeSelected}
      />

      {filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
          No companies match this filter.
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block">
            <ScrapingTable
              rows={filtered}
              selected={selected}
              onToggleSelect={toggleSelect}
              onToggleSelectAll={toggleSelectAll}
              onRetry={handleRetry}
              onViewDiagnostics={handleViewDiagnostics}
            />
          </div>

          {/* Mobile cards */}
          <div className="md:hidden">
            <ScrapingCards
              rows={filtered}
              selected={selected}
              onToggleSelect={toggleSelect}
              onRetry={handleRetry}
              onViewDiagnostics={handleViewDiagnostics}
            />
          </div>
        </>
      )}

    </div>
  )
}
