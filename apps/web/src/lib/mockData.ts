/**
 * Mock data for frontend development.
 * Replace with real API calls when wiring the backend.
 */

import type {
  CampaignRead,
  CompanyCounts,
  StatsResponse,
  ScrapeJobRead,
  RunRead,
  IntegrationHealthItem,
} from './types'

// ── Campaigns ─────────────────────────────────────────────────

export const MOCK_CAMPAIGNS: CampaignRead[] = [
  {
    id: 'camp-001',
    name: 'Series B SaaS — Q2 2026',
    description: 'Outbound targets for Q2 2026 enterprise push',
    upload_count: 3,
    company_count: 2847,
    created_at: '2026-04-01T09:00:00Z',
    updated_at: '2026-05-17T14:22:00Z',
  },
  {
    id: 'camp-002',
    name: 'FinTech Europe — May Batch',
    description: null,
    upload_count: 1,
    company_count: 614,
    created_at: '2026-05-10T11:00:00Z',
    updated_at: '2026-05-15T08:30:00Z',
  },
  {
    id: 'camp-003',
    name: 'APAC Expansion — Q3 Pilot',
    description: 'Early-stage pilot for APAC market entry',
    upload_count: 1,
    company_count: 189,
    created_at: '2026-05-16T07:00:00Z',
    updated_at: '2026-05-16T07:00:00Z',
  },
]

export const MOCK_ACTIVE_CAMPAIGN = MOCK_CAMPAIGNS[0]

// ── Company counts ─────────────────────────────────────────────

export const MOCK_COMPANY_COUNTS: CompanyCounts = {
  total: 2847,
  scrape_not_started: 327,
  scrape_in_progress: 15,
  scrape_cancelled: 4,
  scrape_permanent_fail: 48,
  scrape_soft_fail: 37,
  uploaded: 342,       // not yet scraped — S1 queue
  scraped: 2505,       // scraped, not yet classified — S2 queue
  classified: 1891,    // classified — Possible + Unknown + Crap
  contact_ready: 423,  // Possible, contacts pending — S3 queue
  unlabeled: 187,      // Unknown (need human review)
  possible: 423,
  unknown: 187,
  crap: 1281,
  scrape_done: 2420,
  scrape_failed: 85,
  not_scraped: 342,
}

// ── Pipeline stats ─────────────────────────────────────────────

export const MOCK_STATS: StatsResponse = {
  scrape: {
    total: 2847,
    succeeded: 2420,
    failed: 85,
    site_unavailable: 15,
    running: 15,
    queued: 327,
    stuck_count: 0,
    pct_done: 88,
    avg_job_sec: 4.2,
    eta_seconds: 1380,
    eta_at: null,
  },
  analysis: {
    total: 2505,
    succeeded: 1891,
    failed: 2,
    site_unavailable: 0,
    running: 0,
    queued: 612,
    stuck_count: 0,
    pct_done: 75,
    avg_job_sec: 8.1,
    eta_seconds: null,
    eta_at: null,
  },
  contact_fetch: {
    total: 423,
    succeeded: 389,
    failed: 12,
    site_unavailable: 0,
    running: 3,
    queued: 22,
    stuck_count: 0,
    pct_done: 92,
    avg_job_sec: 12.4,
    eta_seconds: 300,
    eta_at: null,
  },
  validation: {
    total: 1247,
    succeeded: 891,
    failed: 89,
    site_unavailable: 0,
    running: 0,
    queued: 267,
    stuck_count: 0,
    pct_done: 72,
    avg_job_sec: 2.1,
    eta_seconds: null,
    eta_at: null,
  },
  as_of: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
}

// ── Recent scrape jobs ─────────────────────────────────────────

export const MOCK_RECENT_SCRAPE_JOBS: ScrapeJobRead[] = [
  {
    id: 'scrape-001', website_url: 'https://linear.app', normalized_url: 'https://linear.app',
    domain: 'linear.app', state: 'done', terminal_state: true, js_fallback: false,
    include_sitemap: false, general_model: 'gpt-4o-mini', classify_model: 'gpt-4o-mini',
    discovered_urls_count: 12, pages_fetched_count: 8, fetch_failures_count: 0,
    markdown_pages_count: 8, llm_used_count: 1, llm_failed_count: 0,
    last_error_code: null, last_error_message: null,
    created_at: new Date(Date.now() - 1 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 30 * 1000).toISOString(),
    started_at: new Date(Date.now() - 55 * 1000).toISOString(),
    finished_at: new Date(Date.now() - 30 * 1000).toISOString(),
  },
  {
    id: 'scrape-002', website_url: 'https://rippling.com', normalized_url: 'https://rippling.com',
    domain: 'rippling.com', state: 'done', terminal_state: true, js_fallback: true,
    include_sitemap: false, general_model: 'gpt-4o-mini', classify_model: 'gpt-4o-mini',
    discovered_urls_count: 24, pages_fetched_count: 14, fetch_failures_count: 1,
    markdown_pages_count: 13, llm_used_count: 1, llm_failed_count: 0,
    last_error_code: null, last_error_message: null,
    created_at: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    started_at: new Date(Date.now() - 3.5 * 60 * 1000).toISOString(),
    finished_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
  },
  {
    id: 'scrape-003', website_url: 'https://deel.com', normalized_url: 'https://deel.com',
    domain: 'deel.com', state: 'failed', terminal_state: true, js_fallback: false,
    include_sitemap: false, general_model: 'gpt-4o-mini', classify_model: 'gpt-4o-mini',
    discovered_urls_count: 0, pages_fetched_count: 0, fetch_failures_count: 3,
    markdown_pages_count: 0, llm_used_count: 0, llm_failed_count: 0,
    last_error_code: 'TIMEOUT', last_error_message: 'Connection timed out after 30s',
    created_at: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 6 * 60 * 1000).toISOString(),
    started_at: new Date(Date.now() - 7.5 * 60 * 1000).toISOString(),
    finished_at: new Date(Date.now() - 6 * 60 * 1000).toISOString(),
  },
]

// ── Recent AI runs ─────────────────────────────────────────────

export const MOCK_RECENT_RUNS: RunRead[] = [
  {
    id: 'run-001', upload_id: 'upload-001',
    prompt_id: 'prompt-001', prompt_name: 'B2B SaaS Classifier v3',
    general_model: 'gpt-4o-mini', classify_model: 'gpt-4o-mini',
    status: 'done',
    total_jobs: 450, completed_jobs: 450, failed_jobs: 2,
    created_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    started_at: new Date(Date.now() - 44 * 60 * 1000).toISOString(),
    finished_at: new Date(Date.now() - 11 * 60 * 1000).toISOString(),
  },
  {
    id: 'run-002', upload_id: 'upload-002',
    prompt_id: 'prompt-001', prompt_name: 'B2B SaaS Classifier v3',
    general_model: 'gpt-4o-mini', classify_model: 'gpt-4o-mini',
    status: 'running',
    total_jobs: 612, completed_jobs: 187, failed_jobs: 0,
    created_at: new Date(Date.now() - 18 * 60 * 1000).toISOString(),
    started_at: new Date(Date.now() - 17 * 60 * 1000).toISOString(),
    finished_at: null,
  },
]

// ── Services health ────────────────────────────────────────────

export const MOCK_SERVICES_HEALTH: IntegrationHealthItem[] = [
  {
    provider: 'openrouter', label: 'OpenRouter',
    connected: true, credits_remaining: null,
    error_code: '', message: '$14.20 used this session',
  },
  {
    provider: 'apollo', label: 'Apollo',
    connected: true, credits_remaining: 8450,
    error_code: '', message: '',
  },
  {
    provider: 'snov', label: 'Snov.io',
    connected: true, credits_remaining: 2100,
    error_code: '', message: '',
  },
  {
    provider: 'zerobounce', label: 'ZeroBounce',
    connected: true, credits_remaining: 15000,
    error_code: '', message: '',
  },
]

// ── Recent uploads ────────────────────────────────────────────

import type { UploadRead } from './types'

export const MOCK_RECENT_UPLOADS: UploadRead[] = [
  {
    id: 'upload-001', campaign_id: 'camp-001',
    filename: 'series-b-saas-may.csv', checksum: 'abc1',
    row_count: 1500, valid_count: 1487, invalid_count: 13,
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'upload-002', campaign_id: 'camp-001',
    filename: 'saas-batch-2.xlsx', checksum: 'abc2',
    row_count: 847, valid_count: 842, invalid_count: 5,
    created_at: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'upload-003', campaign_id: 'camp-001',
    filename: 'final-additions.csv', checksum: 'abc3',
    row_count: 500, valid_count: 500, invalid_count: 0,
    created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'upload-004', campaign_id: 'camp-002',
    filename: 'fintech-europe.xlsx', checksum: 'abc4',
    row_count: 614, valid_count: 608, invalid_count: 6,
    created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
  },
]

// ── Per-campaign pipeline summaries ───────────────────────────

export interface CampaignPipelineSummary {
  total: number
  notScraped: number
  scraped: number       // scraped but not yet classified
  classified: number    // crap + unknown (not worth pursuing further)
  possible: number      // worth pursuing
  contactsFound: number
  validEmails: number
  lastActivity: string
}

export const MOCK_CAMPAIGN_SUMMARIES: Record<string, CampaignPipelineSummary> = {
  'camp-001': {
    total: 2847, notScraped: 342, scraped: 614, classified: 1468,
    possible: 423, contactsFound: 389, validEmails: 891,
    lastActivity: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
  },
  'camp-002': {
    total: 614, notScraped: 0, scraped: 0, classified: 481,
    possible: 133, contactsFound: 118, validEmails: 94,
    lastActivity: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
  },
  'camp-003': {
    total: 189, notScraped: 189, scraped: 0, classified: 0,
    possible: 0, contactsFound: 0, validEmails: 0,
    lastActivity: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
  },
}

// ── Derived funnel summary ─────────────────────────────────────

export interface FunnelSummary {
  uploaded: number
  scraped: number
  possible: number
  contactsFound: number   // companies with at least one contact
  validEmails: number     // validated deliverable emails
}

export function buildFunnelSummary(
  counts: CompanyCounts,
  stats: StatsResponse,
): FunnelSummary {
  return {
    uploaded:      counts.total,
    scraped:       counts.scraped,
    possible:      counts.possible,
    contactsFound: stats.contact_fetch?.succeeded ?? 0,
    validEmails:   stats.validation?.succeeded ?? 0,
  }
}
