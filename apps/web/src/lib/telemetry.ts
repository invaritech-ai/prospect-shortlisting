import type {
  OperationsEvent,
  OperationsEventStatus,
  RunRead,
  ScrapeJobRead,
} from './types'

function toTimeValue(iso: string): number {
  const value = Date.parse(iso)
  return Number.isFinite(value) ? value : 0
}

function scrapeStatus(job: ScrapeJobRead): OperationsEventStatus {
  const status = job.status.toLowerCase()
  if (!job.terminal_state || status === 'running' || status === 'created') return 'active'
  if (status === 'completed') return 'completed'
  return 'failed'
}

function runStatus(run: RunRead): OperationsEventStatus {
  const status = run.status.toLowerCase()
  if (status === 'running' || status === 'created') return 'active'
  if (status === 'failed' || status === 'dead') return 'failed'
  return 'completed'
}

export function buildOperationsEvents(scrapeJobs: ScrapeJobRead[], runs: RunRead[]): OperationsEvent[] {
  const scrapeEvents: OperationsEvent[] = scrapeJobs.map((job) => {
    const status = scrapeStatus(job)
    const errorCode = job.last_error_code ?? null
    return {
      id: `scrape:${job.id}`,
      kind: 'scrape',
      status,
      occurred_at: job.updated_at || job.created_at,
      title: job.domain,
      subtitle: `${job.id.slice(0, 8)}… · ${job.status}`,
      error_code: errorCode,
      search_blob: `${job.domain} ${job.id} ${job.status} ${errorCode ?? ''}`.toLowerCase(),
      scrape_job: job,
      run: null,
    }
  })

  const runEvents: OperationsEvent[] = runs.map((run) => {
    const status = runStatus(run)
    const errorHint = status === 'failed' ? 'run_failed' : null
    const done = run.completed_jobs + run.failed_jobs
    return {
      id: `analysis:${run.id}`,
      kind: 'analysis',
      status,
      occurred_at: run.finished_at || run.started_at || run.created_at,
      title: run.prompt_name,
      subtitle: `${run.id.slice(0, 8)}… · ${done}/${run.total_jobs} · ${run.failed_jobs} failed`,
      error_code: errorHint,
      search_blob: `${run.prompt_name} ${run.id} ${run.status}`.toLowerCase(),
      scrape_job: null,
      run,
    }
  })

  return [...scrapeEvents, ...runEvents].sort((a, b) => toTimeValue(b.occurred_at) - toTimeValue(a.occurred_at))
}
