import type { ActiveView } from './navigation'
import type { PipelineStageStats, StatsResponse } from './types'

function stageHasWork(stats: PipelineStageStats | undefined): boolean {
  if (!stats) return false
  return (
    stats.running > 0
    || stats.queued > 0
    || stats.succeeded > 0
    || stats.failed > 0
    || (stats.site_unavailable ?? 0) > 0
    || (stats.stuck_count ?? 0) > 0
  )
}

/** True once that stage has seen any queue or terminal job volume (not "never touched"). */
function isStageStartedForDefaultSort(view: ActiveView, stats: StatsResponse | null): boolean {
  if (!stats) return false
  switch (view) {
    case 's1-scraping':
      return stageHasWork(stats.scrape)
    case 's2-ai':
      return stageHasWork(stats.analysis)
    case 's3-contacts':
      return stageHasWork(stats.contact_fetch)
    case 's4-reveal':
      return stageHasWork(stats.contact_reveal)
    case 's5-validation':
      return stageHasWork(stats.validation)
    default:
      return false
  }
}

/** Default sort for company-based pipeline views S1 through S3. */
export function defaultCompanySortForStageView(
  view: ActiveView,
  stats: StatsResponse | null,
): { sortBy: string; sortDir: 'asc' | 'desc' } {
  const started = isStageStartedForDefaultSort(view, stats)
  if (view === 's1-scraping') {
    return started ? { sortBy: 'scrape_updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
  }
  if (view === 's2-ai') {
    return started ? { sortBy: 'analysis_updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
  }
  if (view === 's3-contacts') {
    return started ? { sortBy: 'contact_fetch_updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
  }
  return { sortBy: 'last_activity', sortDir: 'desc' }
}

/** S4 discovered list: domain first, then last_seen freshness when reveal pipeline has started. */
export function defaultDiscoveredSort(stats: StatsResponse | null): { sortBy: string; sortDir: 'asc' | 'desc' } {
  const started = isStageStartedForDefaultSort('s4-reveal', stats)
  return started ? { sortBy: 'last_seen_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
}

/** S5 ProspectContact list (DB-backed). Domain until validation started, then MRU. */
export function defaultValidationContactSort(stats: StatsResponse | null): { sortBy: string; sortDir: 'asc' | 'desc' } {
  const started = isStageStartedForDefaultSort('s5-validation', stats)
  return started ? { sortBy: 'updated_at', sortDir: 'desc' } : { sortBy: 'domain', sortDir: 'asc' }
}
