import type { DomainRead } from '../../../lib/types'
import { formatRelativeTime } from '../shared/relativeTime'

export function relTime(iso: string): string {
  return formatRelativeTime(iso, true)
}

export function failureLabel(row: DomainRead): string | null {
  if ((row.scrape_status ?? 'pending') !== 'failed') return null
  const cls = row.latest_scrape_failure_class
  if (cls === 'permanent') return 'Permanent'
  if (cls === 'transient') return 'Transient'
  if (cls === 'blocked') return 'Blocked'
  if (cls === 'no_content') return 'No content'
  return row.latest_scrape_error_code ?? null
}
