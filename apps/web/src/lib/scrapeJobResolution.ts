import type { ScrapeJobRead } from './types'

export function canRenderScrapeJobPanel(job: ScrapeJobRead): boolean {
  return Boolean(job.domain && job.status && job.updated_at)
}

export async function resolveScrapeJobRead(
  job: ScrapeJobRead,
  loadJob: (jobId: string) => Promise<ScrapeJobRead>,
): Promise<ScrapeJobRead> {
  if (canRenderScrapeJobPanel(job)) return job
  return loadJob(job.id)
}
