import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { listFullPipelineCompanies } from '../../../lib/api'
import type {
  CampaignStageCounts,
  FullPipelineCompanyRow,
} from '../../../lib/types'
import { parseApiError } from '../../../lib/utils'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'

const PAGE_SIZE = 50

interface FullPipelineViewProps {
  campaignId: string
  stageCounts: CampaignStageCounts | null
}

function displayStatus(value: string | null | undefined): string {
  if (!value) return 'Pending'
  return value
    .split(/[_-]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function scrapeLabel(row: FullPipelineCompanyRow): string {
  const status = (row.scrape_status ?? '').toLowerCase()
  if (!status) return 'Pending'
  if (status === 'queued') return 'Queued'
  if (status === 'running') return 'Running'
  if (status === 'succeeded') return 'Done'
  if (status === 'failed' && row.latest_scrape_retryable) return 'Retryable failed'
  if (status === 'failed') return 'Failed'
  return displayStatus(status)
}

function reviewLabel(row: FullPipelineCompanyRow): string {
  if (row.effective_label) return displayStatus(row.effective_label)
  if (row.decision_status) return displayStatus(row.decision_status)
  if (row.scrape_status !== 'succeeded') return 'Waiting'
  return 'Pending'
}

function contactLabel(row: FullPipelineCompanyRow): string {
  const status = (row.fetch_status ?? '').toLowerCase()
  const contactsFound = row.contacts_found
  if (status === 'queued') return 'Queued'
  if (status === 'running') return 'Running'
  if (status === 'failed') return 'Failed'
  if (status === 'succeeded') return contactsFound > 0 ? `${contactsFound.toLocaleString()} contacts` : 'No contacts'
  const effectiveLabel = (row.effective_label ?? row.decision_status ?? '').toLowerCase()
  if (effectiveLabel === 'possible') return 'Pending'
  return 'Not in scope'
}

function statusTone(label: string): 'neutral' | 'live' | 'done' | 'fail' {
  const normalized = label.toLowerCase()
  if (normalized.includes('running') || normalized.includes('queued')) return 'live'
  if (normalized.includes('done') || normalized.includes('possible') || normalized.includes('contacts')) return 'done'
  if (normalized.includes('failed') || normalized.includes('crap')) return 'fail'
  return 'neutral'
}

function toneStyle(tone: 'neutral' | 'live' | 'done' | 'fail'): CSSProperties {
  if (tone === 'live') return { background: 'var(--oc-warn-bg)', color: 'var(--oc-warn-text)', borderColor: 'color-mix(in srgb, var(--oc-warn-text) 25%, white)' }
  if (tone === 'done') return { background: 'var(--oc-success-bg)', color: 'var(--oc-success-text)', borderColor: 'color-mix(in srgb, var(--oc-success-text) 20%, white)' }
  if (tone === 'fail') return { background: 'var(--oc-fail-bg)', color: 'var(--oc-fail-text)', borderColor: 'color-mix(in srgb, var(--oc-fail-text) 20%, white)' }
  return { background: 'var(--oc-surface)', color: 'var(--oc-muted)', borderColor: 'var(--oc-border)' }
}

function StatusPill({ label }: { label: string }) {
  return (
    <span
      style={{
        ...toneStyle(statusTone(label)),
        display: 'inline-flex',
        alignItems: 'center',
        minHeight: '1.5rem',
        border: '1px solid',
        borderRadius: '0.375rem',
        padding: '0.125rem 0.5rem',
        fontSize: '0.75rem',
        fontWeight: 700,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}

function validationSubtext(row: FullPipelineCompanyRow): string {
  if (row.contacts_found === 0) return 'No contacts'
  if (row.email_contact_count === 0) return 'No emails to validate'
  if (row.valid_email_count === row.email_contact_count) return 'All emails valid'
  const remaining = row.email_contact_count - row.valid_email_count
  const emailLabel = remaining === 1 ? 'email' : 'emails'
  return `${remaining.toLocaleString()} ${emailLabel} not valid or unverified`
}

function SummaryMetric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div
      style={{
        borderLeft: `3px solid ${color}`,
        padding: '0.5rem 0.75rem',
        background: 'var(--oc-surface)',
        borderRadius: '0.375rem',
        minWidth: '9.5rem',
      }}
    >
      <div style={{ fontSize: '0.6875rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--oc-muted)' }}>
        {label}
      </div>
      <div style={{ marginTop: '0.25rem', fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 800, color: 'var(--oc-text)' }}>
        {value}
      </div>
    </div>
  )
}

export function FullPipelineView({ campaignId, stageCounts }: FullPipelineViewProps) {
  const [rows, setRows] = useState<FullPipelineCompanyRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setOffset(0)
  }, [campaignId, search])

  useEffect(() => {
    let cancelled = false
    const trimmedSearch = search.trim()
    setIsLoading(true)
    setError('')
    listFullPipelineCompanies(campaignId, {
      search: trimmedSearch,
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        if (cancelled) return
        setRows(page.items)
        setTotal(page.total)
      })
      .catch((err) => {
        if (cancelled) return
        setRows([])
        setTotal(0)
        setError(parseApiError(err))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => { cancelled = true }
  }, [campaignId, offset, search])

  const metrics = useMemo(() => {
    if (!stageCounts) return []
    return [
      { label: 'S1 scraped', value: `${stageCounts.scraping.succeeded.toLocaleString()} / ${stageCounts.scraping.total.toLocaleString()}`, color: 'var(--s1)' },
      { label: 'S2 possible', value: `${stageCounts.ai_review.possible.toLocaleString()} / ${stageCounts.ai_review.all.toLocaleString()}`, color: 'var(--s2)' },
      { label: 'S3 contacts', value: `${stageCounts.contacts.done.toLocaleString()} / ${stageCounts.contacts.all.toLocaleString()}`, color: 'var(--s3)' },
      { label: 'S4 valid', value: `${stageCounts.validation.valid.toLocaleString()} / ${stageCounts.validation.total.toLocaleString()}`, color: 'var(--s5)' },
    ]
  }, [stageCounts])

  const canPrev = offset > 0
  const canNext = offset + PAGE_SIZE < total

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div className="oc-panel" style={{ padding: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <span className="oc-label">Full Pipeline</span>
            <h1 className="oc-heading-page" style={{ margin: '0.25rem 0 0' }}>Company stage status</h1>
          </div>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search domain..."
            className="oc-input"
            style={{ width: 'min(22rem, 100%)' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.625rem', flexWrap: 'wrap', marginTop: '1rem' }}>
          {metrics.map((metric) => (
            <SummaryMetric key={metric.label} {...metric} />
          ))}
        </div>
      </div>

      {error && (
        <div className="oc-panel" style={{ padding: '0.875rem 1rem', borderColor: 'color-mix(in srgb, var(--oc-fail-text) 20%, white)', color: 'var(--oc-fail-text)' }}>
          {error}
        </div>
      )}

      <div className="oc-panel" style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '980px' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--oc-border)' }}>
              <th style={{ padding: '0.75rem' }}>Domain</th>
              <th style={{ padding: '0.75rem' }}>S1 scrape</th>
              <th style={{ padding: '0.75rem' }}>S2 review</th>
              <th style={{ padding: '0.75rem' }}>S3 contacts</th>
              <th style={{ padding: '0.75rem' }}>S4 valid / emails</th>
              <th style={{ padding: '0.75rem' }}>Last activity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const contactsFound = row.contacts_found
              const validCount = row.valid_email_count
              const emailTotal = row.email_contact_count
              const lastActivity = row.last_activity ?? row.latest_contact_updated_at ?? row.latest_scrape_updated_at ?? row.created_at
              return (
                <tr key={row.domain_id} style={{ borderBottom: '1px solid var(--oc-border)' }}>
                  <td style={{ padding: '0.75rem' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', fontWeight: 700, color: 'var(--oc-text)' }}>{row.domain}</div>
                    <div style={{ marginTop: '0.1875rem', fontSize: '0.75rem', color: 'var(--oc-muted)' }}>{row.normalized_url}</div>
                  </td>
                  <td style={{ padding: '0.75rem' }}><StatusPill label={scrapeLabel(row)} /></td>
                  <td style={{ padding: '0.75rem' }}><StatusPill label={reviewLabel(row)} /></td>
                  <td style={{ padding: '0.75rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', alignItems: 'flex-start' }}>
                      <StatusPill label={contactLabel(row)} />
                      {row.emails_found > 0 && (
                        <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>{row.emails_found.toLocaleString()} emails</span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: '0.75rem' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 800, color: emailTotal > 0 ? 'var(--s5)' : 'var(--oc-muted)' }}>
                        {contactsFound > 0 ? `${validCount.toLocaleString()} / ${emailTotal.toLocaleString()}` : '-'}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
                        {validationSubtext(row)}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--oc-muted)', fontSize: '0.8125rem' }}>
                    <RelativeTimeLabel timestamp={lastActivity} prefix="" />
                  </td>
                </tr>
              )
            })}
            {!isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--oc-muted)' }}>
                  No companies found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
          {isLoading
            ? 'Loading...'
            : `Showing ${rows.length.toLocaleString()} of ${total.toLocaleString()} companies`}
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button type="button" className="oc-btn oc-btn-secondary oc-btn-sm" disabled={!canPrev || isLoading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Prev
          </button>
          <button type="button" className="oc-btn oc-btn-secondary oc-btn-sm" disabled={!canNext || isLoading} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
