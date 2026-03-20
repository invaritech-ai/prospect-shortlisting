import type {
  AnalyticsSnapshot,
  CompanyCounts,
  OperationsEvent,
  OperationsEventStatus,
  RunRead,
  ScrapeJobRead,
} from './types'

function toTimeValue(iso: string): number {
  const value = Date.parse(iso)
  return Number.isFinite(value) ? value : 0
}

export function scrapeStatus(job: ScrapeJobRead): OperationsEventStatus {
  const status = job.status.toLowerCase()
  if (!job.terminal_state || status === 'running' || status === 'created') return 'active'
  if (status === 'completed') return 'completed'
  return 'failed'
}

export function runStatus(run: RunRead): OperationsEventStatus {
  const status = run.status.toLowerCase()
  if (status === 'running' || status === 'created') return 'active'
  if (status === 'failed' || status === 'dead') return 'failed'
  return 'completed'
}

export function buildOperationsEvents(scrapeJobs: ScrapeJobRead[], runs: RunRead[]): OperationsEvent[] {
  const scrapeEvents: OperationsEvent[] = scrapeJobs.map((job) => {
    const status = scrapeStatus(job)
    const stage1 = job.stage1_status || '-'
    const stage2 = job.stage2_status || '-'
    const errorCode = job.last_error_code ?? null
    return {
      id: `scrape:${job.id}`,
      kind: 'scrape',
      status,
      occurred_at: job.updated_at || job.created_at,
      title: job.domain,
      subtitle: `${job.id.slice(0, 8)}… · S1:${stage1} · S2:${stage2}`,
      error_code: errorCode,
      search_blob: `${job.domain} ${job.id} ${stage1} ${stage2} ${errorCode ?? ''}`.toLowerCase(),
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

function percent(part: number, total: number): number | null {
  if (total <= 0) return null
  return Math.round((part / total) * 1000) / 10
}

export function buildAnalyticsSnapshot(
  scrapeJobs: ScrapeJobRead[],
  runs: RunRead[],
  counts: CompanyCounts | null,
): AnalyticsSnapshot {
  const scrapeSampleTotal = scrapeJobs.length
  const scrapeSampleCompleted = scrapeJobs.filter((job) => scrapeStatus(job) === 'completed').length
  const scrapeSampleFailed = scrapeJobs.filter((job) => scrapeStatus(job) === 'failed').length
  const scrapeSampleActive = scrapeJobs.filter((job) => scrapeStatus(job) === 'active').length

  const runSampleTotal = runs.length
  const runSampleCompleted = runs.filter((run) => runStatus(run) === 'completed').length
  const runSampleFailed = runs.filter((run) => runStatus(run) === 'failed').length
  const runSampleActive = runs.filter((run) => runStatus(run) === 'active').length

  const possibleRatioPct = counts && counts.total > 0 ? percent(counts.possible, counts.total) : null
  const scrapeFailurePct = percent(scrapeSampleFailed, scrapeSampleTotal)
  const analysisFailurePct = percent(runSampleFailed, runSampleTotal)

  return {
    scrape_sample_total: scrapeSampleTotal,
    scrape_sample_completed: scrapeSampleCompleted,
    scrape_sample_failed: scrapeSampleFailed,
    scrape_sample_active: scrapeSampleActive,
    run_sample_total: runSampleTotal,
    run_sample_completed: runSampleCompleted,
    run_sample_failed: runSampleFailed,
    run_sample_active: runSampleActive,
    possible_ratio_pct: possibleRatioPct,
    scrape_failure_pct: scrapeFailurePct,
    analysis_failure_pct: analysisFailurePct,
  }
}

export type CountBucket = { label: string; count: number }

function topCounts(values: string[], limit: number): CountBucket[] {
  const map = new Map<string, number>()
  for (const value of values) {
    if (!value) continue
    map.set(value, (map.get(value) ?? 0) + 1)
  }
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([label, count]) => ({ label, count }))
}

export function topScrapeErrorCodes(scrapeJobs: ScrapeJobRead[], limit = 6): CountBucket[] {
  const codes = scrapeJobs.map((job) => job.last_error_code ?? '')
  return topCounts(codes, limit)
}

export function topFailedRunPrompts(runs: RunRead[], limit = 6): CountBucket[] {
  const prompts = runs.filter((run) => runStatus(run) === 'failed').map((run) => run.prompt_name)
  return topCounts(prompts, limit)
}
