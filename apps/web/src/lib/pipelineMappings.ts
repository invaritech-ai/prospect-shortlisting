import type { ScrapeFilter, ScrapeSubFilter } from './types'

const SCRAPE_SUB_FILTER_ALIASES: Record<string, ScrapeFilter> = {
  all: 'all',
  'not-started': 'not-started',
  pending: 'not-started',
  'in-progress': 'in-progress',
  active: 'in-progress',
  done: 'done',
  cancelled: 'cancelled',
  permanent: 'permanent',
  'permanent-fail': 'permanent',
  'permanent-failures': 'permanent',
  soft: 'soft',
  'soft-fail': 'soft',
  'soft-failures': 'soft',
  failed: 'soft',
}

export function scrapeSubToFilter(sub: ScrapeSubFilter): ScrapeFilter {
  return SCRAPE_SUB_FILTER_ALIASES[sub] ?? 'all'
}

export function getResumeStageForCompany(company: {
  latest_scrape_status?: string | null
  latest_analysis_status?: string | null
  contact_fetch_status?: string | null
}): 'S1' | 'S2' | 'S3' | null {
  const scrapeStatus = (company.latest_scrape_status ?? '').toLowerCase()
  const analysisStatus = (company.latest_analysis_status ?? '').toLowerCase()
  const contactStatus = (company.contact_fetch_status ?? '').toLowerCase()

  if (
    scrapeStatus === 'failed'
    || scrapeStatus === 'step1_failed'
    || scrapeStatus === 'site_unavailable'
    || scrapeStatus === 'dead'
  ) {
    return 'S1'
  }
  if (analysisStatus === 'failed' || analysisStatus === 'dead') return 'S2'
  if (contactStatus === 'failed') return 'S3'
  return null
}
