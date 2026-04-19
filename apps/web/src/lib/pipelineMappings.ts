import type { ContactStageFilter, S4VerifFilter, ScrapeFilter, ScrapeSubFilter } from './types'

export function scrapeSubToFilter(sub: ScrapeSubFilter): ScrapeFilter {
  if (sub === 'pending') return 'none'
  if (sub === 'done') return 'done'
  if (sub === 'failed') return 'failed'
  return 'all'
}

export function verifFilterToParams(filter: S4VerifFilter): {
  verificationStatus?: string
  stageFilter?: ContactStageFilter
  titleMatch?: boolean
  staleDays?: number
} {
  switch (filter) {
    case 'valid': return { verificationStatus: 'valid' }
    case 'invalid': return { verificationStatus: 'invalid' }
    case 'catch-all': return { verificationStatus: 'catch-all' }
    case 'unverified': return { verificationStatus: 'unverified' }
    case 'campaign_ready': return { stageFilter: 'campaign_ready' }
    case 'title_match': return { titleMatch: true }
    case 'stale_30d': return { staleDays: 30 }
    default: return {}
  }
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
