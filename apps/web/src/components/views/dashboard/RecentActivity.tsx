import type { ScrapeJobRead, RunRead } from '../../../lib/types'

interface RecentActivityProps {
  scrapeJobs: ScrapeJobRead[]
  runs: RunRead[]
  onViewAll: () => void
}

function stateColor(state: string): string {
  if (state === 'done')    return 'var(--oc-success-text)'
  if (state === 'failed')  return 'var(--oc-fail-text)'
  if (state === 'running') return 'var(--s1)'
  return 'var(--oc-muted)'
}

function runStatusColor(status: string): string {
  if (status === 'done')    return 'var(--oc-success-text)'
  if (status === 'running') return 'var(--s2)'
  if (status === 'failed')  return 'var(--oc-fail-text)'
  return 'var(--oc-muted)'
}

export function RecentActivity({ scrapeJobs, runs, onViewAll }: RecentActivityProps) {
  const hasItems = scrapeJobs.length > 0 || runs.length > 0
  if (!hasItems) return null

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.875rem' }}>
        <p className="oc-label" style={{ margin: 0 }}>Recent Activity</p>
        <button type="button" onClick={onViewAll}
          style={{ fontSize: '0.75rem', color: 'var(--oc-accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit', fontWeight: 500 }}>
          View all →
        </button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
        {scrapeJobs.slice(0, 2).map((job) => (
          <div key={job.id} className="oc-activity-row">
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 700, color: 'var(--s1)', flexShrink: 0, minWidth: '1.5rem' }}>S1</span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.9375rem', color: 'var(--oc-text)' }}>{job.domain}</span>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, flexShrink: 0, color: stateColor(job.state) }}>{job.state}</span>
          </div>
        ))}
        {runs.slice(0, 2).map((run) => (
          <div key={run.id} className="oc-activity-row">
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 700, color: 'var(--s2)', flexShrink: 0, minWidth: '1.5rem' }}>S2</span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.9375rem', color: 'var(--oc-text)' }}>{run.prompt_name}</span>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, flexShrink: 0, color: runStatusColor(run.status) }}>
              {run.status === 'running' ? `${run.completed_jobs}/${run.total_jobs}` : run.status}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
