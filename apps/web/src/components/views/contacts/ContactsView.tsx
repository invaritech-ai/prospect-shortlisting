import { useState, useMemo } from 'react'
import { MOCK_CONTACT_ROWS, MOCK_CONTACT_STATS, MOCK_STATS } from '../../../lib/useAppData'
import type { MockContactRow, ContactFetchStatus } from '../../../lib/useAppData'
import type { StatsResponse } from '../../../lib/types'
import { StageViewHeader }        from '../shared/StageViewHeader'
import { StageToolbar }           from '../shared/StageToolbar'
import { ContactsTable }          from './ContactsTable'
import { ContactsCards }          from './ContactsCards'
import { ContactDrawer }          from './ContactDrawer'
import { ContactsSettingsDrawer } from './ContactsSettingsDrawer'

type FilterValue = 'all' | ContactFetchStatus

const FILTERS = [
  { value: 'all',      label: 'All' },
  { value: 'pending',  label: 'Pending' },
  { value: 'running',  label: 'Fetching', color: 'var(--s3)' },
  { value: 'done',     label: 'Done',     color: 'var(--oc-success-text)' },
  { value: 'failed',   label: 'Failed',   color: 'var(--oc-fail-text)' },
  { value: 'no_match', label: 'No match', color: 'var(--oc-warn-text)' },
]

interface ContactsViewProps {
  stats?: StatsResponse | null
}

export function ContactsView({ stats: rawStats }: ContactsViewProps) {
  const stats = rawStats ?? MOCK_STATS

  const [filter, setFilter]       = useState<FilterValue>('all')
  const [search, setSearch]       = useState('')
  const [selected, setSelected]   = useState<Set<string>>(new Set())
  const [viewingRow, setViewingRow]     = useState<MockContactRow | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const contactStats = [
    { label: 'pending',  value: MOCK_CONTACT_STATS.pending,  color: 'var(--oc-muted)' },
    { label: 'fetching', value: MOCK_CONTACT_STATS.running,  color: 'var(--s3)', live: MOCK_CONTACT_STATS.running > 0 },
    { label: 'done',     value: MOCK_CONTACT_STATS.done,     color: 'var(--oc-success-text)' },
    { label: 'contacts', value: MOCK_CONTACT_STATS.totalContacts, color: 'var(--s3)' },
    { label: 'emails',   value: MOCK_CONTACT_STATS.totalEmails,   color: 'var(--oc-success-text)' },
  ]

  const filtered = useMemo(() => {
    let rows = MOCK_CONTACT_ROWS
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

  const pendingCount = MOCK_CONTACT_STATS.pending + MOCK_CONTACT_STATS.failed
  const etaSecs = stats.contact_fetch?.eta_seconds ?? null

  const bulkActions = [
    { label: 'Fetch contacts', onClick: () => { console.log('Bulk fetch', [...selected]); setSelected(new Set()) } },
  ]

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <StageViewHeader
          stageNum="S3"
          stageLabel="Contacts & Email"
          stageColor="var(--s3)"
          stageBg="var(--s3-bg)"
          stats={contactStats}
          etaSeconds={etaSecs}
          onOpenSettings={() => setSettingsOpen(true)}
          settingsLabel="Title rules"
          primaryAction={pendingCount > 0 ? {
            label: `Fetch ${pendingCount} pending`,
            onClick: () => console.log('Fetch all pending'),
          } : undefined}
          secondaryAction={MOCK_CONTACT_STATS.failed > 0 ? {
            label: `Retry ${MOCK_CONTACT_STATS.failed} failed`,
            onClick: () => setFilter('failed'),
          } : undefined}
        />

        <StageToolbar
          stageColor="var(--s3)"
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
            No companies match this filter.
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <ContactsTable
                rows={filtered}
                selected={selected}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                onFetch={(id) => console.log('Fetch:', id)}
                onViewContacts={setViewingRow}
              />
            </div>
            <div className="md:hidden">
              <ContactsCards
                rows={filtered}
                selected={selected}
                onToggleSelect={toggleSelect}
                onFetch={(id) => console.log('Fetch:', id)}
                onViewContacts={setViewingRow}
              />
            </div>
          </>
        )}

      </div>

      <ContactDrawer row={viewingRow} onClose={() => setViewingRow(null)} />
      <ContactsSettingsDrawer isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  )
}
