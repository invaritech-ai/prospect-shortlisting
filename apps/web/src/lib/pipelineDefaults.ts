import type { ActiveView } from './navigation'
import type { ScrapeSubFilter } from './types'

export function getDefaultPipelineScrapeSubFilter(_activeView: ActiveView): ScrapeSubFilter {
  return 'all'
}
