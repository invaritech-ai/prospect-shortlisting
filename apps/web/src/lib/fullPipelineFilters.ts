import type { CompanyListItem } from './types'

/** Status chips on Full Pipeline — must stay aligned with `FullPipelineView` filter UI. */
export type FullPipelineStatusFilter =
  | 'all'
  | 'not-started'
  | 'in-progress'
  | 'cancelled'
  | 'complete'
  | 'has-failures'
  | 'permanent-failures'
  | 'soft-failures'

export function matchesFullPipelineFilters(
  c: CompanyListItem,
  statusFilter: FullPipelineStatusFilter,
  search: string,
): boolean {
  const q = search.trim().toLowerCase()
  if (q && !c.domain.toLowerCase().includes(q)) return false

  if (statusFilter === 'all') return true

  const scrape = c.latest_scrape_status?.toLowerCase()
  const analysis = c.latest_analysis_status?.toLowerCase()
  const contact = c.contact_fetch_status?.toLowerCase()

  if (statusFilter === 'not-started') return !scrape
  if (statusFilter === 'cancelled') return scrape === 'cancelled'
  if (statusFilter === 'in-progress')
    return (
      scrape === 'created'
      || analysis === 'queued'
      || analysis === 'running'
      || contact === 'queued'
      || contact === 'running'
    )
  if (statusFilter === 'complete')
    return scrape === 'completed' && !!(c.feedback_manual_label ?? c.latest_decision)
  if (statusFilter === 'has-failures')
    return (
      scrape === 'failed'
      || scrape === 'step1_failed'
      || scrape === 'site_unavailable'
      || analysis === 'failed'
      || analysis === 'dead'
      || contact === 'failed'
    )
  if (statusFilter === 'permanent-failures') return scrape === 'site_unavailable'
  if (statusFilter === 'soft-failures')
    return scrape === 'failed' || scrape === 'step1_failed' || scrape === 'dead' || analysis === 'failed' || contact === 'failed'
  return true
}

export function companyListBrowseUrl(c: CompanyListItem): string {
  const u = (c.normalized_url ?? '').trim() || (c.raw_url ?? '').trim()
  if (u) return u
  return `https://${c.domain}`
}
