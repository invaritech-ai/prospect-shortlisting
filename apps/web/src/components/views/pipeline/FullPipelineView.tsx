import { useMemo, useState } from 'react'
import { MOCK_FULL_PIPELINE_COMPANIES } from '../../../lib/useAppData'
import type { CompanyListItem } from '../../../lib/types'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'

type StageFilter = 'all' | 'uploaded' | 'scraped' | 'contact_ready'

const FILTERS: Array<{ value: StageFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'uploaded', label: 'Uploaded' },
  { value: 'scraped', label: 'Scraped' },
  { value: 'contact_ready', label: 'Contact Ready' },
]

function scrapeLabel(c: CompanyListItem): string {
  const status = (c.latest_scrape_status ?? '').toLowerCase()
  if (!status) return '—'
  if (status === 'completed') return 'Done'
  if (status === 'running') return 'Running'
  if (status === 'created') return 'Queued'
  if (status === 'failed' || status === 'site_unavailable' || status === 'step1_failed') return 'Failed'
  return status
}

function decisionLabel(c: CompanyListItem): string {
  const label = c.feedback_manual_label ?? c.latest_decision
  return label ? String(label) : '—'
}

export function FullPipelineView() {
  const [stageFilter, setStageFilter] = useState<StageFilter>('all')
  const [search, setSearch] = useState('')

  const rows = useMemo(() => {
    let list = MOCK_FULL_PIPELINE_COMPANIES
    if (stageFilter !== 'all') {
      list = list.filter((r) => r.pipeline_stage === stageFilter)
    }
    if (search.trim()) {
      const term = search.toLowerCase().trim()
      list = list.filter((r) => r.domain.toLowerCase().includes(term))
    }
    return list
  }, [stageFilter, search])

  const stats = useMemo(
    () => ({
      uploaded: MOCK_FULL_PIPELINE_COMPANIES.filter((r) => r.pipeline_stage === 'uploaded').length,
      scraped: MOCK_FULL_PIPELINE_COMPANIES.filter((r) => r.pipeline_stage === 'scraped').length,
      contactReady: MOCK_FULL_PIPELINE_COMPANIES.filter((r) => r.pipeline_stage === 'contact_ready').length,
    }),
    [],
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div className="oc-panel" style={{ padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
          <span className="oc-label">Full Pipeline</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
            {rows.length.toLocaleString()} rows
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
          <span className="oc-badge">Uploaded: {stats.uploaded}</span>
          <span className="oc-badge">Scraped: {stats.scraped}</span>
          <span className="oc-badge">Contact Ready: {stats.contactReady}</span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              className="oc-btn oc-btn-secondary oc-btn-xs"
              style={stageFilter === f.value ? { borderColor: 'var(--oc-accent)', color: 'var(--oc-accent)' } : undefined}
              onClick={() => setStageFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search domain..."
            className="oc-input"
            style={{ marginLeft: 'auto', minWidth: '220px' }}
          />
        </div>
      </div>

      <div className="oc-panel" style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '900px' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--oc-border)' }}>
              <th style={{ padding: '0.625rem' }}>Domain</th>
              <th style={{ padding: '0.625rem' }}>Stage</th>
              <th style={{ padding: '0.625rem' }}>S1</th>
              <th style={{ padding: '0.625rem' }}>S2</th>
              <th style={{ padding: '0.625rem' }}>Contacts</th>
              <th style={{ padding: '0.625rem' }}>Emails</th>
              <th style={{ padding: '0.625rem' }}>Last Activity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} style={{ borderBottom: '1px solid var(--oc-border)' }}>
                <td style={{ padding: '0.625rem', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>{row.domain}</td>
                <td style={{ padding: '0.625rem' }}>{row.pipeline_stage}</td>
                <td style={{ padding: '0.625rem' }}>{scrapeLabel(row)}</td>
                <td style={{ padding: '0.625rem' }}>{decisionLabel(row)}</td>
                <td style={{ padding: '0.625rem' }}>{row.discovered_contact_count}</td>
                <td style={{ padding: '0.625rem' }}>{row.contact_count}</td>
                <td style={{ padding: '0.625rem' }}>
                  <RelativeTimeLabel timestamp={row.last_activity} prefix="" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
