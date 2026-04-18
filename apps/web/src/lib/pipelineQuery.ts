import type { ActiveView } from './navigation'
import type { CompanyStageFilter, DecisionFilter } from './types'

const PIPELINE_STAGE_MAP: Partial<Record<ActiveView, CompanyStageFilter>> = {
  's1-scraping': 'all',
  's2-ai': 'has_scrape',
  's3-contacts': 'has_scrape',
}

export function getPipelineCompanyQuery(
  activeView: ActiveView,
  decisionFilter: DecisionFilter,
): { stageFilter: CompanyStageFilter; decisionFilter: DecisionFilter } | null {
  const stageFilter = PIPELINE_STAGE_MAP[activeView]
  if (stageFilter == null) return null

  return {
    stageFilter,
    decisionFilter: activeView === 's1-scraping' ? 'all' : decisionFilter,
  }
}
