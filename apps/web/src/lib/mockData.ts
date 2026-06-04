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
    scrape_count: 2100,
    classified_count: 1800,
    possible_count: 620,
    contact_count: 410,
    created_at: '2026-04-01T09:00:00Z',
    updated_at: '2026-05-17T14:22:00Z',
  },
  {
    id: 'camp-002',
    name: 'FinTech Europe — May Batch',
    description: null,
    upload_count: 1,
    company_count: 614,
    scrape_count: 300,
    classified_count: 200,
    possible_count: 80,
    contact_count: 50,
    created_at: '2026-05-10T11:00:00Z',
    updated_at: '2026-05-15T08:30:00Z',
  },
  {
    id: 'camp-003',
    name: 'APAC Expansion — Q3 Pilot',
    description: 'Early-stage pilot for APAC market entry',
    upload_count: 1,
    company_count: 189,
    scrape_count: 0,
    classified_count: 0,
    possible_count: 0,
    contact_count: 0,
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

// ── Scraping view rows ────────────────────────────────────────

export type ScrapeStatus = 'pending' | 'running' | 'done' | 'failed'

export interface MockScrapeRow {
  id: string
  domain: string
  url: string
  status: ScrapeStatus
  pagesCount: number
  errorCode: string | null
  durationSec: number | null
  updatedAt: string
}

const t = (minAgo: number) => new Date(Date.now() - minAgo * 60_000).toISOString()

export const MOCK_SCRAPE_ROWS: MockScrapeRow[] = [
  { id: 'sc-01', domain: 'linear.app',       url: 'https://linear.app',        status: 'done',    pagesCount: 8,  errorCode: null,      durationSec: 12, updatedAt: t(2)  },
  { id: 'sc-02', domain: 'rippling.com',     url: 'https://rippling.com',      status: 'running', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(0) },
  { id: 'sc-03', domain: 'deel.com',         url: 'https://deel.com',          status: 'failed',  pagesCount: 0,  errorCode: 'TIMEOUT', durationSec: 30, updatedAt: t(6)  },
  { id: 'sc-04', domain: 'notion.so',        url: 'https://notion.so',         status: 'done',    pagesCount: 14, errorCode: null,      durationSec: 18, updatedAt: t(4)  },
  { id: 'sc-05', domain: 'figma.com',        url: 'https://figma.com',         status: 'done',    pagesCount: 11, errorCode: null,      durationSec: 9,  updatedAt: t(5)  },
  { id: 'sc-06', domain: 'vercel.com',       url: 'https://vercel.com',        status: 'running', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(1) },
  { id: 'sc-07', domain: 'stripe.com',       url: 'https://stripe.com',        status: 'pending', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(60) },
  { id: 'sc-08', domain: 'github.com',       url: 'https://github.com',        status: 'pending', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(60) },
  { id: 'sc-09', domain: 'retool.com',       url: 'https://retool.com',        status: 'done',    pagesCount: 9,  errorCode: null,      durationSec: 14, updatedAt: t(8)  },
  { id: 'sc-10', domain: 'airtable.com',     url: 'https://airtable.com',      status: 'failed',  pagesCount: 0,  errorCode: 'BOT_BLOCK', durationSec: 8, updatedAt: t(12) },
  { id: 'sc-11', domain: 'planetscale.com',  url: 'https://planetscale.com',   status: 'done',    pagesCount: 6,  errorCode: null,      durationSec: 7,  updatedAt: t(9)  },
  { id: 'sc-12', domain: 'loom.com',         url: 'https://loom.com',          status: 'pending', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(60) },
  { id: 'sc-13', domain: 'supabase.com',     url: 'https://supabase.com',      status: 'running', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(0) },
  { id: 'sc-14', domain: 'turso.tech',       url: 'https://turso.tech',        status: 'done',    pagesCount: 5,  errorCode: null,      durationSec: 6,  updatedAt: t(11) },
  { id: 'sc-15', domain: 'neon.tech',        url: 'https://neon.tech',         status: 'done',    pagesCount: 7,  errorCode: null,      durationSec: 8,  updatedAt: t(13) },
  { id: 'sc-16', domain: 'cal.com',          url: 'https://cal.com',           status: 'failed',  pagesCount: 0,  errorCode: 'TIMEOUT', durationSec: 30, updatedAt: t(20) },
  { id: 'sc-17', domain: 'dub.co',           url: 'https://dub.co',            status: 'pending', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(60) },
  { id: 'sc-18', domain: 'resend.com',       url: 'https://resend.com',        status: 'done',    pagesCount: 4,  errorCode: null,      durationSec: 5,  updatedAt: t(15) },
  { id: 'sc-19', domain: 'posthog.com',      url: 'https://posthog.com',       status: 'done',    pagesCount: 12, errorCode: null,      durationSec: 16, updatedAt: t(16) },
  { id: 'sc-20', domain: 'mintlify.com',     url: 'https://mintlify.com',      status: 'pending', pagesCount: 0,  errorCode: null,      durationSec: null, updatedAt: t(60) },
]

export const MOCK_SCRAPE_STATS = {
  pending: MOCK_SCRAPE_ROWS.filter((r) => r.status === 'pending').length,
  running: MOCK_SCRAPE_ROWS.filter((r) => r.status === 'running').length,
  done:    MOCK_SCRAPE_ROWS.filter((r) => r.status === 'done').length,
  failed:  MOCK_SCRAPE_ROWS.filter((r) => r.status === 'failed').length,
}

// ── Recent uploads ────────────────────────────────────────────

import type { UploadRead } from './types'

export const MOCK_RECENT_UPLOADS: UploadRead[] = [
  {
    id: 'upload-001', campaign_id: 'camp-001',
    filename: 'series-b-saas-may.csv',
    row_count: 1500,
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'upload-002', campaign_id: 'camp-001',
    filename: 'saas-batch-2.xlsx',
    row_count: 847,
    created_at: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'upload-003', campaign_id: 'camp-001',
    filename: 'final-additions.csv',
    row_count: 500,
    created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'upload-004', campaign_id: 'camp-002',
    filename: 'fintech-europe.xlsx',
    row_count: 614,
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

// ── AI Review rows ────────────────────────────────────────────

export type AIVerdict = 'Unclassified' | 'Possible' | 'Unknown' | 'Crap'

export interface MockAIRow {
  id: string
  domain: string
  url: string
  verdict: AIVerdict
  confidence: number        // 0–100
  reasoning: string         // short excerpt from LLM
  pagesReviewed: number
  updatedAt: string
}

const tAI = (minAgo: number) => new Date(Date.now() - minAgo * 60_000).toISOString()

export const MOCK_AI_ROWS: MockAIRow[] = [
  { id: 'ai-01', domain: 'linear.app',       url: 'https://linear.app',        verdict: 'Possible',  confidence: 94, reasoning: 'B2B project management SaaS, clear enterprise tier, strong growth signals.',  pagesReviewed: 8,  updatedAt: tAI(3)  },
  { id: 'ai-02', domain: 'rippling.com',     url: 'https://rippling.com',      verdict: 'Possible',  confidence: 91, reasoning: 'HR & payroll platform targeting mid-market. ICP match for our segment.',         pagesReviewed: 14, updatedAt: tAI(4)  },
  { id: 'ai-03', domain: 'deel.com',         url: 'https://deel.com',          verdict: 'Possible',  confidence: 87, reasoning: 'Global payroll and compliance — strong B2B signals, $12B valuation.',            pagesReviewed: 11, updatedAt: tAI(5)  },
  { id: 'ai-04', domain: 'notion.so',        url: 'https://notion.so',         verdict: 'Possible',  confidence: 82, reasoning: 'Horizontal productivity tool, strong enterprise adoption. Worth pursuing.',        pagesReviewed: 9,  updatedAt: tAI(6)  },
  { id: 'ai-05', domain: 'figma.com',        url: 'https://figma.com',         verdict: 'Possible',  confidence: 79, reasoning: 'Design platform with broad B2B adoption. Enterprise tier is our fit.',             pagesReviewed: 12, updatedAt: tAI(7)  },
  { id: 'ai-06', domain: 'vercel.com',       url: 'https://vercel.com',        verdict: 'Possible',  confidence: 88, reasoning: 'Developer infrastructure, strong enterprise motion. High ICP score.',               pagesReviewed: 7,  updatedAt: tAI(8)  },
  { id: 'ai-07', domain: 'stripe.com',       url: 'https://stripe.com',        verdict: 'Possible',  confidence: 96, reasoning: 'Payments infrastructure — classic B2B, massive enterprise base.',                  pagesReviewed: 15, updatedAt: tAI(9)  },
  { id: 'ai-08', domain: 'retool.com',       url: 'https://retool.com',        verdict: 'Unknown',   confidence: 55, reasoning: 'Internal tool builder — B2B but unclear if target segment aligns.',               pagesReviewed: 6,  updatedAt: tAI(10) },
  { id: 'ai-09', domain: 'airtable.com',     url: 'https://airtable.com',      verdict: 'Unknown',   confidence: 48, reasoning: 'No-code platform, mixed B2B/B2C signals. Needs human review.',                    pagesReviewed: 8,  updatedAt: tAI(11) },
  { id: 'ai-10', domain: 'planetscale.com',  url: 'https://planetscale.com',   verdict: 'Unknown',   confidence: 52, reasoning: 'Database platform — technical but unclear enterprise motion.',                      pagesReviewed: 5,  updatedAt: tAI(12) },
  { id: 'ai-11', domain: 'loom.com',         url: 'https://loom.com',          verdict: 'Unknown',   confidence: 44, reasoning: 'Video messaging, broad market — hard to score without more data.',                  pagesReviewed: 4,  updatedAt: tAI(13) },
  { id: 'ai-12', domain: 'cal.com',          url: 'https://cal.com',           verdict: 'Unknown',   confidence: 41, reasoning: 'Open-source scheduling — unclear monetisation and segment fit.',                    pagesReviewed: 3,  updatedAt: tAI(14) },
  { id: 'ai-13', domain: 'supabase.com',     url: 'https://supabase.com',      verdict: 'Unknown',   confidence: 57, reasoning: 'Firebase alternative — developer focus, growing enterprise. Borderline.',          pagesReviewed: 7,  updatedAt: tAI(15) },
  { id: 'ai-14', domain: 'dub.co',           url: 'https://dub.co',            verdict: 'Crap',      confidence: 12, reasoning: 'Link shortener — consumer focus, no clear B2B enterprise signals.',                pagesReviewed: 2,  updatedAt: tAI(16) },
  { id: 'ai-15', domain: 'resend.com',       url: 'https://resend.com',        verdict: 'Crap',      confidence: 18, reasoning: 'Email API for developers — too niche/PLG, not our ICP.',                           pagesReviewed: 4,  updatedAt: tAI(17) },
  { id: 'ai-16', domain: 'mintlify.com',     url: 'https://mintlify.com',      verdict: 'Crap',      confidence: 9,  reasoning: 'Documentation tool — small TAM, developer-only, no enterprise signals.',            pagesReviewed: 3,  updatedAt: tAI(18) },
  { id: 'ai-17', domain: 'turso.tech',       url: 'https://turso.tech',        verdict: 'Crap',      confidence: 11, reasoning: 'Edge SQLite database — very early, PLG motion only.',                              pagesReviewed: 3,  updatedAt: tAI(19) },
  { id: 'ai-18', domain: 'neon.tech',        url: 'https://neon.tech',         verdict: 'Crap',      confidence: 15, reasoning: 'Serverless Postgres — developer tool, no enterprise evidence found.',               pagesReviewed: 4,  updatedAt: tAI(20) },
  { id: 'ai-19', domain: 'posthog.com',      url: 'https://posthog.com',       verdict: 'Unknown',   confidence: 63, reasoning: 'Product analytics — self-serve model, some enterprise. Borderline case.',           pagesReviewed: 12, updatedAt: tAI(22) },
  { id: 'ai-20', domain: 'github.com',       url: 'https://github.com',        verdict: 'Possible',  confidence: 98, reasoning: 'Platform used by virtually every software company — universal enterprise fit.',     pagesReviewed: 10, updatedAt: tAI(25) },
]

export const MOCK_AI_STATS = {
  possible: MOCK_AI_ROWS.filter((r) => r.verdict === 'Possible').length,
  unknown:  MOCK_AI_ROWS.filter((r) => r.verdict === 'Unknown').length,
  crap:     MOCK_AI_ROWS.filter((r) => r.verdict === 'Crap').length,
  running:  0,
}

// ── Derived funnel summary ─────────────────────────────────────

export interface FunnelSummary {
  uploaded: number
  scraped: number
  possible: number
  contactsFound: number   // companies with at least one contact
  validEmails: number     // validated deliverable emails
}

// ── Contacts & Email rows ─────────────────────────────────────

export type ContactFetchStatus = 'pending' | 'running' | 'done' | 'failed' | 'no_match'

export interface MockContact {
  id: string
  name: string
  title: string
  email: string | null
  linkedinUrl: string | null
}

export interface MockContactRow {
  id: string
  domain: string
  url: string
  status: ContactFetchStatus
  contactsFound: number
  emailsFound: number
  contacts: MockContact[]
  updatedAt: string
}

const tC = (minAgo: number) => new Date(Date.now() - minAgo * 60_000).toISOString()

export const MOCK_CONTACT_ROWS: MockContactRow[] = [
  {
    id: 'cr-01', domain: 'linear.app', url: 'https://linear.app',
    status: 'done', contactsFound: 4, emailsFound: 3, updatedAt: tC(5),
    contacts: [
      { id: 'c-01a', name: 'Karri Saarinen', title: 'CEO & Co-founder', email: 'karri@linear.app', linkedinUrl: 'https://linkedin.com/in/karri' },
      { id: 'c-01b', name: 'Tuomas Artman', title: 'CTO & Co-founder', email: 'tuomas@linear.app', linkedinUrl: 'https://linkedin.com/in/tuomas' },
      { id: 'c-01c', name: 'Jori Lallo', title: 'Co-founder', email: null, linkedinUrl: 'https://linkedin.com/in/jori' },
      { id: 'c-01d', name: 'Emily Nakamura', title: 'VP Engineering', email: 'emily@linear.app', linkedinUrl: null },
    ],
  },
  {
    id: 'cr-02', domain: 'rippling.com', url: 'https://rippling.com',
    status: 'done', contactsFound: 3, emailsFound: 2, updatedAt: tC(8),
    contacts: [
      { id: 'c-02a', name: 'Parker Conrad', title: 'CEO & Co-founder', email: 'parker@rippling.com', linkedinUrl: 'https://linkedin.com/in/parkerconrad' },
      { id: 'c-02b', name: 'Prasanna Sankar', title: 'CTO & Co-founder', email: null, linkedinUrl: 'https://linkedin.com/in/prasanna' },
      { id: 'c-02c', name: 'Matt MacInnis', title: 'COO', email: 'matt@rippling.com', linkedinUrl: 'https://linkedin.com/in/mattmacinnis' },
    ],
  },
  {
    id: 'cr-03', domain: 'deel.com', url: 'https://deel.com',
    status: 'done', contactsFound: 5, emailsFound: 4, updatedAt: tC(12),
    contacts: [
      { id: 'c-03a', name: 'Alex Bouaziz', title: 'CEO & Co-founder', email: 'alex@deel.com', linkedinUrl: 'https://linkedin.com/in/alexbouaziz' },
      { id: 'c-03b', name: 'Shuo Wang', title: 'CTO', email: 'shuo@deel.com', linkedinUrl: 'https://linkedin.com/in/shuowang' },
      { id: 'c-03c', name: 'Nadia Vatalidis', title: 'VP People', email: 'nadia@deel.com', linkedinUrl: 'https://linkedin.com/in/nadia' },
      { id: 'c-03d', name: 'Ryan Breslow', title: 'VP Sales', email: null, linkedinUrl: 'https://linkedin.com/in/ryanbreslow' },
      { id: 'c-03e', name: 'Dana Kuo', title: 'Head of Engineering', email: 'dana@deel.com', linkedinUrl: null },
    ],
  },
  {
    id: 'cr-04', domain: 'notion.so', url: 'https://notion.so',
    status: 'done', contactsFound: 2, emailsFound: 2, updatedAt: tC(15),
    contacts: [
      { id: 'c-04a', name: 'Ivan Zhao', title: 'CEO & Co-founder', email: 'ivan@makenotion.com', linkedinUrl: 'https://linkedin.com/in/ivanz' },
      { id: 'c-04b', name: 'Simon Last', title: 'Co-founder & CTO', email: 'simon@makenotion.com', linkedinUrl: 'https://linkedin.com/in/simonlast' },
    ],
  },
  {
    id: 'cr-05', domain: 'figma.com', url: 'https://figma.com',
    status: 'running', contactsFound: 0, emailsFound: 0, updatedAt: tC(1),
    contacts: [],
  },
  {
    id: 'cr-06', domain: 'vercel.com', url: 'https://vercel.com',
    status: 'done', contactsFound: 3, emailsFound: 3, updatedAt: tC(18),
    contacts: [
      { id: 'c-06a', name: 'Guillermo Rauch', title: 'CEO & Founder', email: 'rauchg@vercel.com', linkedinUrl: 'https://linkedin.com/in/guillermo' },
      { id: 'c-06b', name: 'Malte Ubl', title: 'CTO', email: 'malte@vercel.com', linkedinUrl: 'https://linkedin.com/in/malteubl' },
      { id: 'c-06c', name: 'Lee Robinson', title: 'VP Product', email: 'lee@vercel.com', linkedinUrl: 'https://linkedin.com/in/leerob' },
    ],
  },
  {
    id: 'cr-07', domain: 'stripe.com', url: 'https://stripe.com',
    status: 'failed', contactsFound: 0, emailsFound: 0, updatedAt: tC(22),
    contacts: [],
  },
  {
    id: 'cr-08', domain: 'retool.com', url: 'https://retool.com',
    status: 'done', contactsFound: 2, emailsFound: 1, updatedAt: tC(25),
    contacts: [
      { id: 'c-08a', name: 'David Hsu', title: 'CEO & Co-founder', email: 'david@retool.com', linkedinUrl: 'https://linkedin.com/in/davidhsu' },
      { id: 'c-08b', name: 'Alex Xiao', title: 'CTO & Co-founder', email: null, linkedinUrl: 'https://linkedin.com/in/alexxi' },
    ],
  },
  {
    id: 'cr-09', domain: 'github.com', url: 'https://github.com',
    status: 'no_match', contactsFound: 0, emailsFound: 0, updatedAt: tC(30),
    contacts: [],
  },
  {
    id: 'cr-10', domain: 'posthog.com', url: 'https://posthog.com',
    status: 'pending', contactsFound: 0, emailsFound: 0, updatedAt: tC(60),
    contacts: [],
  },
  {
    id: 'cr-11', domain: 'supabase.com', url: 'https://supabase.com',
    status: 'pending', contactsFound: 0, emailsFound: 0, updatedAt: tC(60),
    contacts: [],
  },
  {
    id: 'cr-12', domain: 'planetscale.com', url: 'https://planetscale.com',
    status: 'pending', contactsFound: 0, emailsFound: 0, updatedAt: tC(60),
    contacts: [],
  },
]

export const MOCK_CONTACT_STATS = {
  pending:  MOCK_CONTACT_ROWS.filter((r) => r.status === 'pending').length,
  running:  MOCK_CONTACT_ROWS.filter((r) => r.status === 'running').length,
  done:     MOCK_CONTACT_ROWS.filter((r) => r.status === 'done').length,
  failed:   MOCK_CONTACT_ROWS.filter((r) => r.status === 'failed').length,
  no_match: MOCK_CONTACT_ROWS.filter((r) => r.status === 'no_match').length,
  totalContacts: MOCK_CONTACT_ROWS.reduce((s, r) => s + r.contactsFound, 0),
  totalEmails:   MOCK_CONTACT_ROWS.reduce((s, r) => s + r.emailsFound, 0),
}

// ── Full pipeline mock companies ──────────────────────────────

import type { CompanyListItem } from './types'

const tP = (hrsAgo: number) => new Date(Date.now() - hrsAgo * 3_600_000).toISOString()

export const MOCK_FULL_PIPELINE_COMPANIES: CompanyListItem[] = [
  { id: 'co-01', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://linear.app',    normalized_url: 'https://linear.app',    domain: 'linear.app',    pipeline_stage: 'contact_ready', created_at: tP(72), last_activity: tP(0.1), latest_decision: 'Possible', latest_confidence: 94, latest_scrape_job_id: 's1',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a1',  latest_analysis_status: 'succeeded', latest_analysis_terminal: true,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 3, discovered_contact_count: 4, discovered_title_matched_count: 4, revealed_contact_count: 3, revealed_title_matched_count: 3, contact_fetch_status: 'succeeded' },
  { id: 'co-02', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://rippling.com',  normalized_url: 'https://rippling.com',  domain: 'rippling.com',  pipeline_stage: 'contact_ready', created_at: tP(72), last_activity: tP(0.2), latest_decision: 'Possible', latest_confidence: 91, latest_scrape_job_id: 's2',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a2',  latest_analysis_status: 'succeeded', latest_analysis_terminal: true,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 2, discovered_contact_count: 3, discovered_title_matched_count: 3, revealed_contact_count: 2, revealed_title_matched_count: 2, contact_fetch_status: 'succeeded' },
  { id: 'co-03', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://deel.com',      normalized_url: 'https://deel.com',      domain: 'deel.com',      pipeline_stage: 'contact_ready', created_at: tP(72), last_activity: tP(0.3), latest_decision: 'Possible', latest_confidence: 87, latest_scrape_job_id: 's3',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a3',  latest_analysis_status: 'succeeded', latest_analysis_terminal: true,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 4, discovered_contact_count: 5, discovered_title_matched_count: 5, revealed_contact_count: 4, revealed_title_matched_count: 4, contact_fetch_status: 'succeeded' },
  { id: 'co-04', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://notion.so',     normalized_url: 'https://notion.so',     domain: 'notion.so',     pipeline_stage: 'contact_ready', created_at: tP(48), last_activity: tP(0.5), latest_decision: 'Possible', latest_confidence: 82, latest_scrape_job_id: 's4',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a4',  latest_analysis_status: 'succeeded', latest_analysis_terminal: true,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 2, discovered_contact_count: 2, discovered_title_matched_count: 2, revealed_contact_count: 2, revealed_title_matched_count: 2, contact_fetch_status: 'succeeded' },
  { id: 'co-05', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://vercel.com',    normalized_url: 'https://vercel.com',    domain: 'vercel.com',    pipeline_stage: 'contact_ready', created_at: tP(48), last_activity: tP(1),   latest_decision: 'Possible', latest_confidence: 88, latest_scrape_job_id: 's5',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a5',  latest_analysis_status: 'succeeded', latest_analysis_terminal: true,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 3, discovered_contact_count: 3, discovered_title_matched_count: 3, revealed_contact_count: 3, revealed_title_matched_count: 3, contact_fetch_status: 'succeeded' },
  { id: 'co-06', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://figma.com',     normalized_url: 'https://figma.com',     domain: 'figma.com',     pipeline_stage: 'scraped',       created_at: tP(48), last_activity: tP(0.1), latest_decision: 'Possible', latest_confidence: 79, latest_scrape_job_id: 's6',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a6',  latest_analysis_status: 'running',   latest_analysis_terminal: false, feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 0, discovered_contact_count: 0, discovered_title_matched_count: 0, revealed_contact_count: 0, revealed_title_matched_count: 0, contact_fetch_status: null },
  { id: 'co-07', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://retool.com',    normalized_url: 'https://retool.com',    domain: 'retool.com',    pipeline_stage: 'scraped',       created_at: tP(36), last_activity: tP(2),   latest_decision: 'Unknown',  latest_confidence: 55, latest_scrape_job_id: 's7',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a7',  latest_analysis_status: 'succeeded', latest_analysis_terminal: true,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 0, discovered_contact_count: 0, discovered_title_matched_count: 0, revealed_contact_count: 0, revealed_title_matched_count: 0, contact_fetch_status: null },
  { id: 'co-08', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://stripe.com',    normalized_url: 'https://stripe.com',    domain: 'stripe.com',    pipeline_stage: 'scraped',       created_at: tP(36), last_activity: tP(3),   latest_decision: null,       latest_confidence: null, latest_scrape_job_id: 's8',  latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a8',  latest_analysis_status: 'queued',    latest_analysis_terminal: false, feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 0, discovered_contact_count: 0, discovered_title_matched_count: 0, revealed_contact_count: 0, revealed_title_matched_count: 0, contact_fetch_status: null },
  { id: 'co-09', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://airtable.com',  normalized_url: 'https://airtable.com',  domain: 'airtable.com',  pipeline_stage: 'uploaded',      created_at: tP(24), last_activity: tP(12),  latest_decision: null,       latest_confidence: null, latest_scrape_job_id: 's9',  latest_scrape_status: 'failed',    latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: null,  latest_analysis_job_id: null,  latest_analysis_status: null,        latest_analysis_terminal: null,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: 'BOT_BLOCK', latest_scrape_failure_reason: 'Bot blocked', contact_count: 0, discovered_contact_count: 0, discovered_title_matched_count: 0, revealed_contact_count: 0, revealed_title_matched_count: 0, contact_fetch_status: null },
  { id: 'co-10', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://posthog.com',   normalized_url: 'https://posthog.com',   domain: 'posthog.com',   pipeline_stage: 'uploaded',      created_at: tP(24), last_activity: tP(24),  latest_decision: null,       latest_confidence: null, latest_scrape_job_id: null,  latest_scrape_status: null,        latest_scrape_terminal: null,  latest_analysis_pipeline_run_id: null,  latest_analysis_job_id: null,  latest_analysis_status: null,        latest_analysis_terminal: null,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 0, discovered_contact_count: 0, discovered_title_matched_count: 0, revealed_contact_count: 0, revealed_title_matched_count: 0, contact_fetch_status: null },
  { id: 'co-11', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://supabase.com',  normalized_url: 'https://supabase.com',  domain: 'supabase.com',  pipeline_stage: 'uploaded',      created_at: tP(12), last_activity: tP(0.1), latest_decision: null,       latest_confidence: null, latest_scrape_job_id: 's11', latest_scrape_status: 'running',   latest_scrape_terminal: false, latest_analysis_pipeline_run_id: null,  latest_analysis_job_id: null,  latest_analysis_status: null,        latest_analysis_terminal: null,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 0, discovered_contact_count: 0, discovered_title_matched_count: 0, revealed_contact_count: 0, revealed_title_matched_count: 0, contact_fetch_status: null },
  { id: 'co-12', upload_id: 'u1', upload_filename: 'batch.csv', raw_url: 'https://github.com',    normalized_url: 'https://github.com',    domain: 'github.com',    pipeline_stage: 'contact_ready', created_at: tP(96), last_activity: tP(0.5), latest_decision: 'Possible', latest_confidence: 98, latest_scrape_job_id: 's12', latest_scrape_status: 'completed', latest_scrape_terminal: true,  latest_analysis_pipeline_run_id: 'r1', latest_analysis_job_id: 'a12', latest_analysis_status: 'succeeded', latest_analysis_terminal: true,  feedback_thumbs: null, feedback_comment: null, feedback_manual_label: null, latest_scrape_error_code: null, latest_scrape_failure_reason: null, contact_count: 0, discovered_contact_count: 0, discovered_title_matched_count: 0, revealed_contact_count: 0, revealed_title_matched_count: 0, contact_fetch_status: 'succeeded' },
]

// ── Mock integration settings ─────────────────────────────────

import type { IntegrationsStatusResponse } from './types'

const tI = (hrsAgo: number) => new Date(Date.now() - hrsAgo * 3_600_000).toISOString()

export const MOCK_INTEGRATIONS_STATUS: IntegrationsStatusResponse = {
  store_available: true,
  providers: [
    { provider: 'openrouter', label: 'OpenRouter', description: 'LLM routing for AI classification',      fields: [{ field: 'api_key',       is_set: true,  source: 'db',  last4: 'a4f2', updated_at: tI(48) }] },
    { provider: 'apollo',     label: 'Apollo',     description: 'Contact discovery — US & global',        fields: [{ field: 'api_key',       is_set: true,  source: 'env', last4: 'b9c1', updated_at: tI(96) }] },
    { provider: 'snov',       label: 'Snov.io',    description: 'Contact discovery — European focus',     fields: [{ field: 'client_id', is_set: true, source: 'db', last4: '3d7e', updated_at: tI(24) }, { field: 'client_secret', is_set: true, source: 'db', last4: 'f1a9', updated_at: tI(24) }] },
    { provider: 'zerobounce', label: 'ZeroBounce', description: 'Email validation & deliverability',      fields: [{ field: 'api_key',       is_set: false, source: '',    last4: null,   updated_at: null   }] },
  ],
}

// ── Derived funnel summary ─────────────────────────────────────

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
