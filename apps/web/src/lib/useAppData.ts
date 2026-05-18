/**
 * Central data access hook — returns real data when available,
 * falls back to mock data while the backend isn't wired.
 *
 * Components import from here, not directly from mockData.ts.
 * Swap out the mock fallbacks here once real API calls are connected.
 */

import type { CampaignRead, CompanyCounts, StatsResponse } from './types'
import {
  MOCK_CAMPAIGNS,
  MOCK_ACTIVE_CAMPAIGN,
  MOCK_COMPANY_COUNTS,
  MOCK_STATS,
  MOCK_SERVICES_HEALTH,
  MOCK_RECENT_UPLOADS,
  MOCK_RECENT_SCRAPE_JOBS,
  MOCK_RECENT_RUNS,
  MOCK_SCRAPE_ROWS,
  MOCK_SCRAPE_STATS,
  MOCK_CAMPAIGN_SUMMARIES,
  MOCK_AI_ROWS,
  MOCK_AI_STATS,
  MOCK_CONTACT_ROWS,
  MOCK_CONTACT_STATS,
  MOCK_VALIDATION_ROWS,
  MOCK_VALIDATION_STATS,
  MOCK_FULL_PIPELINE_COMPANIES,
  MOCK_INTEGRATIONS_STATUS,
  buildFunnelSummary,
} from './mockData'

// Re-export types that components reference from this module.
export type { CampaignPipelineSummary, FunnelSummary, ScrapeStatus, MockScrapeRow, AIVerdict, MockAIRow, ContactFetchStatus, MockContact, MockContactRow, ValidationStatus, MockValidationRow } from './mockData'

// Re-export mock data through this module so no component
// ever imports from mockData.ts directly.
export {
  MOCK_CAMPAIGNS,
  MOCK_ACTIVE_CAMPAIGN,
  MOCK_COMPANY_COUNTS,
  MOCK_STATS,
  MOCK_SERVICES_HEALTH,
  MOCK_RECENT_UPLOADS,
  MOCK_RECENT_SCRAPE_JOBS,
  MOCK_RECENT_RUNS,
  MOCK_SCRAPE_ROWS,
  MOCK_SCRAPE_STATS,
  MOCK_CAMPAIGN_SUMMARIES,
  MOCK_AI_ROWS,
  MOCK_AI_STATS,
  MOCK_CONTACT_ROWS,
  MOCK_CONTACT_STATS,
  MOCK_VALIDATION_ROWS,
  MOCK_VALIDATION_STATS,
  MOCK_FULL_PIPELINE_COMPANIES,
  MOCK_INTEGRATIONS_STATUS,
  buildFunnelSummary,
}

/** Resolve real-or-mock campaigns. */
export function resolveCampaigns(real: CampaignRead[]): CampaignRead[] {
  return real.length ? real : MOCK_CAMPAIGNS
}

/** Resolve real-or-mock company counts. */
export function resolveCounts(real: CompanyCounts | null): CompanyCounts {
  return real ?? MOCK_COMPANY_COUNTS
}

/** Resolve real-or-mock pipeline stats. */
export function resolveStats(real: StatsResponse | null): StatsResponse {
  return real ?? MOCK_STATS
}
