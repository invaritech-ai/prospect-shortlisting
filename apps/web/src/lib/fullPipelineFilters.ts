import type { CompanyListItem } from './types'

export type FullPipelineStatusFilter =
  | 'all'
  | 'not-started'
  | 'in-progress'
  | 'cancelled'
  | 'complete'
  | 'has-failures'
  | 'permanent-failures'
  | 'soft-failures'

export function companyListBrowseUrl(c: CompanyListItem): string {
  const u = (c.normalized_url ?? '').trim() || (c.raw_url ?? '').trim()
  if (u) return u
  return `https://${c.domain}`
}
