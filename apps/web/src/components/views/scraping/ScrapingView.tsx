import { useState, useMemo } from 'react'
import { MOCK_SCRAPE_ROWS, MOCK_SCRAPE_STATS, MOCK_STATS } from '../../../lib/useAppData'
import type { MockScrapeRow } from '../../../lib/useAppData'
import type { StatsResponse } from '../../../lib/types'
import { StageViewHeader }       from '../shared/StageViewHeader'
import { ScrapingToolbar }        from './ScrapingToolbar'
import { ScrapingTable }          from './ScrapingTable'
import { ScrapingCards }          from './ScrapingCards'
import { ScrapedContentDrawer }   from './ScrapedContentDrawer'
import { ScrapingSettingsDrawer } from './ScrapingSettingsDrawer'
import type { FilterValue }       from './ScrapingToolbar'

interface ScrapingViewProps {
  stats?: StatsResponse | null
}

export function ScrapingView({ stats: rawStats }: ScrapingViewProps) {
  const stats = rawStats ?? MOCK_STATS

  const [filter, setFilter]   = useState<FilterValue>('all')
  const [search, setSearch]   = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [viewingRow, setViewingRow]     = useState<MockScrapeRow | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const scrapeStats = [
    { label: 'pending', value: MOCK_SCRAPE_STATS.pending },
    { label: 'running', value: MOCK_SCRAPE_STATS.running, live: true, color: 'var(--s1)' },
    { label: 'done',    value: MOCK_SCRAPE_STATS.done,    color: 'var(--oc-success-text)' },
    { label: 'failed',  value: MOCK_SCRAPE_STATS.failed,  color: 'var(--oc-fail-text)' },
  ]

  const filtered = useMemo(() => {
    let rows = MOCK_SCRAPE_ROWS
    if (filter !== 'all') rows = rows.filter((r) => r.status === filter)
    if (search.trim())    rows = rows.filter((r) => r.domain.toLowerCase().includes(search.toLowerCase()))
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

  const hasFailed  = MOCK_SCRAPE_STATS.failed > 0
  const hasPending = MOCK_SCRAPE_STATS.pending > 0
  const etaSecs    = stats.scrape.eta_seconds ?? null

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <StageViewHeader
          stageNum="S1"
          stageLabel="Scraping"
          stageColor="var(--s1)"
          stageBg="var(--s1-bg)"
          stats={scrapeStats}
          etaSeconds={etaSecs}
          onOpenSettings={() => setSettingsOpen(true)}
          settingsLabel="Rules"
          primaryAction={hasPending ? {
            label: `Scrape ${MOCK_SCRAPE_STATS.pending.toLocaleString()} pending`,
            onClick: () => console.log('Scrape all pending'),
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
          onScrapeSelected={() => { console.log('Scrape selected:', [...selected]); setSelected(new Set()) }}
        />

        {filtered.length === 0 ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            No companies match this filter.
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <ScrapingTable
                rows={filtered}
                selected={selected}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                onRetry={(id) => console.log('Retry:', id)}
                onViewContent={(row) => setViewingRow(row)}
              />
            </div>
            <div className="md:hidden">
              <ScrapingCards
                rows={filtered}
                selected={selected}
                onToggleSelect={toggleSelect}
                onRetry={(id) => console.log('Retry:', id)}
                onViewDiagnostics={(row) => setViewingRow(row)}
              />
            </div>
          </>
        )}

      </div>

      <ScrapedContentDrawer row={viewingRow} onClose={() => setViewingRow(null)} />
      <ScrapingSettingsDrawer isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  )
}
