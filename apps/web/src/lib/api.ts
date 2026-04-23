import type {
  AnalysisJobDetailRead,
  AnalysisRunJobRead,
  CampaignCreate,
  CampaignList,
  CampaignRead,
  CampaignUpdate,
  CompanyCounts,
  CompanyDeleteResult,
  CompanyIdsResult,
  CompanyList,
  CompanyScrapeResult,
  CompanyStageFilter,
  CostStatsResponse,
  ContactCompanyListResponse,
  ContactCountsResponse,
  ContactFetchResult,
  ContactListResponse,
  ContactStageFilter,
  ContactVerifyRequest,
  ContactVerifyResult,
  DecisionFilter,
  DrainQueueResult,
  FeedbackRead,
  FeedbackUpsert,
  IntegrationsStatusResponse,
  IntegrationProviderId,
  IntegrationProviderStatus,
  IntegrationProviderUpdateRequest,
  IntegrationTestResponse,

  LetterCounts,
  PromptCreate,
  PromptRead,
  PromptUpdate,
  PipelineCostSummaryRead,
  PipelineRunProgressRead,
  PipelineRunStartRequest,
  PipelineRunStartResponse,
  ScrapePromptCreate,
  ScrapePromptRead,
  ScrapePromptUpdate,
  ResetStuckResult,
  RunCreateRequest,
  RunCreateResult,
  RunRead,
  ScrapeFilter,
  ScrapeJobCreate,
  ScrapeJobRead,
  ScrapeRules,
  ScrapePageContentRead,
  StatsResponse,
  TitleMatchRuleCreate,
  TitleMatchRuleRead,
  TitleRuleImpactPreview,
  TitleRuleSeedResult,
  TitleTestResult,
  TitleRuleStatsResponse,
  UploadCompanyList,
  UploadCreateResult,
  UploadDetail,
  UploadList,
  MatchGapFilter,
} from './types'
import type { FullPipelineStatusFilter } from './fullPipelineFilters'

const viteEnv = (import.meta as { env?: Record<string, string | undefined> }).env
const API_BASE_URL = (
  viteEnv?.VITE_API_BASE_URL ??
  (globalThis as { __API_BASE_URL__?: string }).__API_BASE_URL__ ??
  'http://localhost:8000'
).replace(/\/+$/, '')
type ScrapeJobFilter = 'all' | 'active' | 'completed' | 'failed'

interface ApiSessionConfig {
  getAccessToken?: () => string | null
  onUnauthorized?: () => void
}

export interface AuthUserRead {
  email: string
  display_name?: string | null
}

export interface AuthLoginResponse {
  user: AuthUserRead
  access_token?: string | null
  token_type?: string | null
}

let apiSessionConfig: ApiSessionConfig = {}

export function configureApiSession(config: ApiSessionConfig): void {
  apiSessionConfig = config
}

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(`API error ${status}`)
    this.status = status
    this.detail = detail
  }
}

/** Older API builds reject `last_activity` / `updated_at` sort — retry with these. */
const LEGACY_COMPANY_SORT = { sortBy: 'domain' as const, sortDir: 'asc' as const }
const LEGACY_CONTACT_SORT = { sortBy: 'domain' as const, sortDir: 'asc' as const }

let companyListLegacySortFallback = false
let contactsListLegacySortFallback = false
let sortCompatUserNotice: string | null = null

function is422InvalidSortBy(err: unknown): boolean {
  if (!(err instanceof ApiError) || err.status !== 422) return false
  const d = err.detail
  const text =
    typeof d === 'string'
      ? d
      : Array.isArray(d)
        ? JSON.stringify(d)
        : d != null && typeof d === 'object'
          ? JSON.stringify(d)
          : ''
  return /invalid sort_by|sort_by/i.test(text)
}

/** Call after a successful `listCompanies` if you need to sync UI sort to legacy fields. */
export function consumeCompanyListLegacySortFallback(): boolean {
  const v = companyListLegacySortFallback
  companyListLegacySortFallback = false
  return v
}

/** Call after a successful `listContacts` if you need to sync UI sort to legacy fields. */
export function consumeContactsListLegacySortFallback(): boolean {
  const v = contactsListLegacySortFallback
  contactsListLegacySortFallback = false
  return v
}

/** One-line notice when we had to fall back (older backend). */
export function consumeSortCompatUserNotice(): string | null {
  const m = sortCompatUserNotice
  sortCompatUserNotice = null
  return m
}

function recordSortCompatFallback(kind: 'companies' | 'contacts'): void {
  sortCompatUserNotice =
    kind === 'companies'
      ? 'This API build does not support activity-based company sort; using domain order until the backend is redeployed.'
      : 'This API build does not support contact “modified” sort; using domain order until the backend is redeployed.'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = apiSessionConfig.getAccessToken?.() ?? null
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: init?.credentials ?? 'include',
  })
  if (response.status === 204) {
    if (!response.ok) throw new ApiError(response.status, null)
    return undefined as T
  }
  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    if (response.status === 401) apiSessionConfig.onUnauthorized?.()
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body as { detail: unknown }).detail
        : body
    throw new ApiError(response.status, detail)
  }
  return body as T
}

export async function uploadFile(file: File): Promise<UploadCreateResult> {
  return uploadFileToCampaign(file)
}

export async function uploadFileToCampaign(file: File, campaignId?: string): Promise<UploadCreateResult> {
  const form = new FormData()
  form.append('file', file)
  if (campaignId) form.append('campaign_id', campaignId)
  return request<UploadCreateResult>('/v1/uploads', {
    method: 'POST',
    body: form,
  })
}

export async function getUpload(uploadId: string): Promise<UploadDetail> {
  return request<UploadDetail>(`/v1/uploads/${uploadId}`)
}

export async function listUploads(limit = 20, offset = 0): Promise<UploadList> {
  return request<UploadList>(`/v1/uploads?limit=${limit}&offset=${offset}`)
}

export async function listCampaigns(limit = 50, offset = 0): Promise<CampaignList> {
  return request<CampaignList>(`/v1/campaigns?limit=${limit}&offset=${offset}`)
}

export async function createCampaign(payload: CampaignCreate): Promise<CampaignRead> {
  return request<CampaignRead>('/v1/campaigns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateCampaign(campaignId: string, payload: CampaignUpdate): Promise<CampaignRead> {
  return request<CampaignRead>(`/v1/campaigns/${campaignId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteCampaign(campaignId: string): Promise<void> {
  await request<void>(`/v1/campaigns/${campaignId}`, { method: 'DELETE' })
}

export async function assignUploadsToCampaign(campaignId: string, uploadIds: string[]): Promise<CampaignRead> {
  return request<CampaignRead>(`/v1/campaigns/${campaignId}/assign-uploads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ upload_ids: uploadIds }),
  })
}

export async function listCompanies(
  campaignId: string,
  limit = 25,
  offset = 0,
  decisionFilter: DecisionFilter = 'all',
  includeTotal = false,
  scrapeFilter: ScrapeFilter = 'all',
  stageFilter: CompanyStageFilter = 'all',
  letter: string | null = null,
  sortBy = 'last_activity',
  sortDir: 'asc' | 'desc' = 'desc',
  uploadId?: string,
  letters?: string[],
  statusFilter: FullPipelineStatusFilter = 'all',
  search = '',
): Promise<CompanyList> {
  const buildUrl = (sb: string, sd: string) => {
    const params = new URLSearchParams({
      campaign_id: campaignId,
      limit: String(limit),
      offset: String(offset),
      decision_filter: decisionFilter,
      scrape_filter: scrapeFilter,
      stage_filter: stageFilter,
      include_total: includeTotal ? 'true' : 'false',
      sort_by: sb,
      sort_dir: sd,
    })
    if (letter) params.set('letter', letter)
    if (letters && letters.length > 0) params.set('letters', letters.join(','))
    if (uploadId) params.set('upload_id', uploadId)
    const q = search.trim()
    if (q) params.set('search', q)
    if (statusFilter !== 'all') params.set('status_filter', statusFilter)
    return `/v1/companies?${params.toString()}`
  }

  companyListLegacySortFallback = false
  try {
    return await request<CompanyList>(buildUrl(sortBy, sortDir))
  } catch (err) {
    const alreadyLegacy =
      sortBy === LEGACY_COMPANY_SORT.sortBy && sortDir === LEGACY_COMPANY_SORT.sortDir
    if (is422InvalidSortBy(err) && !alreadyLegacy) {
      companyListLegacySortFallback = true
      recordSortCompatFallback('companies')
      return await request<CompanyList>(buildUrl(LEGACY_COMPANY_SORT.sortBy, LEGACY_COMPANY_SORT.sortDir))
    }
    throw err
  }
}

export async function deleteCompanies(campaignId: string, companyIds: string[]): Promise<CompanyDeleteResult> {
  return request<CompanyDeleteResult>('/v1/companies/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ campaign_id: campaignId, company_ids: companyIds }),
  })
}

export async function scrapeSelectedCompanies(
  campaignId: string,
  companyIds: string[],
  options: { scrapeRules?: ScrapeRules; uploadId?: string; idempotencyKey?: string } = {},
): Promise<CompanyScrapeResult> {
  return request<CompanyScrapeResult>('/v1/companies/scrape-selected', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.idempotencyKey ? { 'X-Idempotency-Key': options.idempotencyKey } : {}),
    },
    body: JSON.stringify({
      campaign_id: campaignId,
      company_ids: companyIds,
      scrape_rules: options.scrapeRules,
      upload_id: options.uploadId,
    }),
  })
}

export async function scrapeAllCompanies(
  options: { uploadId?: string; idempotencyKey?: string; scrapeRules?: ScrapeRules } = {},
): Promise<CompanyScrapeResult> {
  return request<CompanyScrapeResult>('/v1/companies/scrape-all', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.idempotencyKey ? { 'X-Idempotency-Key': options.idempotencyKey } : {}),
    },
    body: JSON.stringify({
      upload_id: options.uploadId,
      scrape_rules: options.scrapeRules,
    }),
  })
}

export async function getUploadCompanies(uploadId: string, limit = 25, offset = 0): Promise<UploadCompanyList> {
  return request<UploadCompanyList>(`/v1/uploads/${uploadId}/companies?limit=${limit}&offset=${offset}`)
}

export async function createScrapeJob(payload: ScrapeJobCreate): Promise<ScrapeJobRead> {
  return request<ScrapeJobRead>('/v1/scrape-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}


export async function getScrapeJob(jobId: string): Promise<ScrapeJobRead> {
  return request<ScrapeJobRead>(`/v1/scrape-jobs/${jobId}`)
}

export async function listScrapeJobs(limit = 50, offset = 0, statusFilter: ScrapeJobFilter = 'all', search = ''): Promise<ScrapeJobRead[]> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), status_filter: statusFilter })
  if (search.trim()) params.set('search', search.trim())
  return request<ScrapeJobRead[]>(`/v1/scrape-jobs?${params}`)
}

export async function listScrapeJobPageContents(jobId: string, limit = 200, offset = 0): Promise<ScrapePageContentRead[]> {
  return request<ScrapePageContentRead[]>(`/v1/scrape-jobs/${jobId}/pages-content?limit=${limit}&offset=${offset}`)
}

export async function listPrompts(enabledOnly = false): Promise<PromptRead[]> {
  return request<PromptRead[]>(`/v1/prompts?enabled_only=${enabledOnly ? 'true' : 'false'}`)
}

export async function createPrompt(payload: PromptCreate): Promise<PromptRead> {
  return request<PromptRead>('/v1/prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updatePrompt(promptId: string, payload: PromptUpdate): Promise<PromptRead> {
  return request<PromptRead>(`/v1/prompts/${promptId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deletePrompt(promptId: string): Promise<void> {
  await request<void>(`/v1/prompts/${promptId}`, { method: 'DELETE' })
}

export async function listScrapePrompts(enabledOnly = false): Promise<ScrapePromptRead[]> {
  return request<ScrapePromptRead[]>(`/v1/scrape-prompts?enabled_only=${enabledOnly ? 'true' : 'false'}`)
}

export async function createScrapePrompt(payload: ScrapePromptCreate): Promise<ScrapePromptRead> {
  return request<ScrapePromptRead>('/v1/scrape-prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateScrapePrompt(promptId: string, payload: ScrapePromptUpdate): Promise<ScrapePromptRead> {
  return request<ScrapePromptRead>(`/v1/scrape-prompts/${promptId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteScrapePrompt(promptId: string): Promise<void> {
  await request<void>(`/v1/scrape-prompts/${promptId}`, { method: 'DELETE' })
}

export async function activateScrapePrompt(promptId: string): Promise<ScrapePromptRead> {
  return request<ScrapePromptRead>(`/v1/scrape-prompts/${promptId}/activate`, {
    method: 'POST',
  })
}

export async function createRuns(payload: RunCreateRequest): Promise<RunCreateResult> {
  return request<RunCreateResult>('/v1/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function startPipelineRun(payload: PipelineRunStartRequest): Promise<PipelineRunStartResponse> {
  return request<PipelineRunStartResponse>('/v1/pipeline-runs/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getPipelineRunProgress(runId: string): Promise<PipelineRunProgressRead> {
  return request<PipelineRunProgressRead>(`/v1/pipeline-runs/${encodeURIComponent(runId)}/progress`)
}

export async function getPipelineRunCosts(runId: string): Promise<PipelineCostSummaryRead> {
  return request<PipelineCostSummaryRead>(`/v1/pipeline-runs/${encodeURIComponent(runId)}/costs`)
}

export async function getCampaignCosts(campaignId: string): Promise<PipelineCostSummaryRead> {
  return request<PipelineCostSummaryRead>(`/v1/campaigns/${encodeURIComponent(campaignId)}/costs`)
}

export async function listRuns(limit = 25, offset = 0): Promise<RunRead[]> {
  return request<RunRead[]>(`/v1/runs?limit=${limit}&offset=${offset}`)
}

export async function listRunJobs(runId: string, limit = 500, offset = 0): Promise<AnalysisRunJobRead[]> {
  return request<AnalysisRunJobRead[]>(`/v1/runs/${runId}/jobs?limit=${limit}&offset=${offset}`)
}

export async function getAnalysisJobDetail(analysisJobId: string): Promise<AnalysisJobDetailRead> {
  return request<AnalysisJobDetailRead>(`/v1/analysis-jobs/${analysisJobId}`)
}

export async function getStats(campaignId: string, uploadId?: string): Promise<StatsResponse> {
  const params = new URLSearchParams()
  params.set('campaign_id', campaignId)
  if (uploadId) params.set('upload_id', uploadId)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<StatsResponse>(`/v1/stats${suffix}`)
}

export async function getCostStats(
  options: { campaignId: string; windowDays?: number; uploadId?: string; limit?: number; offset?: number },
): Promise<CostStatsResponse> {
  const params = new URLSearchParams()
  if (options.campaignId) params.set('campaign_id', options.campaignId)
  if (options.windowDays) params.set('window_days', String(options.windowDays))
  if (options.uploadId) params.set('upload_id', options.uploadId)
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  return request<CostStatsResponse>(`/v1/stats/costs?${params.toString()}`)
}

export async function drainQueue(): Promise<DrainQueueResult> {
  return request<DrainQueueResult>('/v1/queue/drain', { method: 'POST' })
}

export async function resetStuckJobs(): Promise<ResetStuckResult> {
  return request<ResetStuckResult>('/v1/jobs/reset-stuck', { method: 'POST' })
}

export async function resetStuckAnalysisJobs(): Promise<ResetStuckResult> {
  return request<ResetStuckResult>('/v1/analysis-jobs/reset-stuck', { method: 'POST' })
}

export async function getCompanyCounts(campaignId: string, uploadId?: string): Promise<CompanyCounts> {
  const params = new URLSearchParams()
  params.set('campaign_id', campaignId)
  if (uploadId) params.set('upload_id', uploadId)
  return request<CompanyCounts>(`/v1/companies/counts?${params.toString()}`)
}

export function getCompaniesExportUrl(campaignId: string): string {
  return `${API_BASE_URL}/v1/companies/export.csv?campaign_id=${encodeURIComponent(campaignId)}`
}

export async function upsertCompanyFeedback(companyId: string, payload: FeedbackUpsert): Promise<FeedbackRead> {
  return request<FeedbackRead>(`/v1/companies/${companyId}/feedback`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listCompanyIds(
  campaignId: string,
  decisionFilter: DecisionFilter = 'all',
  scrapeFilter: ScrapeFilter = 'all',
  stageFilter: CompanyStageFilter = 'all',
  letter: string | null = null,
  uploadId?: string,
  letters?: string[],
  statusFilter: FullPipelineStatusFilter = 'all',
  search = '',
): Promise<CompanyIdsResult> {
  const params = new URLSearchParams({
    campaign_id: campaignId,
    decision_filter: decisionFilter,
    scrape_filter: scrapeFilter,
    stage_filter: stageFilter,
  })
  if (letter) params.set('letter', letter)
  if (letters && letters.length > 0) params.set('letters', letters.join(','))
  if (uploadId) params.set('upload_id', uploadId)
  const q = search.trim()
  if (q) params.set('search', q)
  if (statusFilter !== 'all') params.set('status_filter', statusFilter)
  return request<CompanyIdsResult>(`/v1/companies/ids?${params.toString()}`)
}

export async function getLetterCounts(
  campaignId: string,
  decisionFilter: DecisionFilter = 'all',
  scrapeFilter: ScrapeFilter = 'all',
  stageFilter: CompanyStageFilter = 'all',
  uploadId?: string,
  statusFilter: FullPipelineStatusFilter = 'all',
  search = '',
): Promise<LetterCounts> {
  const params = new URLSearchParams({
    campaign_id: campaignId,
    decision_filter: decisionFilter,
    scrape_filter: scrapeFilter,
    stage_filter: stageFilter,
  })
  if (uploadId) params.set('upload_id', uploadId)
  const q = search.trim()
  if (q) params.set('search', q)
  if (statusFilter !== 'all') params.set('status_filter', statusFilter)
  return request<LetterCounts>(`/v1/companies/letter-counts?${params.toString()}`)
}

// ── Contacts ──────────────────────────────────────────────────────────────────

export async function fetchContactsForCompany(campaignId: string, companyId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/companies/${companyId}/fetch-contacts?campaign_id=${encodeURIComponent(campaignId)}`, { method: 'POST' })
}

export async function fetchContactsForRun(campaignId: string, runId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/runs/${runId}/fetch-contacts?campaign_id=${encodeURIComponent(campaignId)}`, { method: 'POST' })
}

export async function fetchContactsForCompanyApollo(campaignId: string, companyId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/companies/${companyId}/fetch-contacts/apollo?campaign_id=${encodeURIComponent(campaignId)}`, { method: 'POST' })
}

export async function fetchContactsForRunApollo(campaignId: string, runId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/runs/${runId}/fetch-contacts/apollo?campaign_id=${encodeURIComponent(campaignId)}`, { method: 'POST' })
}

export async function fetchContactsSelected(
  campaignId: string,
  companyIds: string[],
  source: 'snov' | 'apollo' | 'both',
  options: { idempotencyKey?: string } = {},
): Promise<ContactFetchResult> {
  return request<ContactFetchResult>('/v1/companies/fetch-contacts-selected', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.idempotencyKey ? { 'X-Idempotency-Key': options.idempotencyKey } : {}),
    },
    body: JSON.stringify({ campaign_id: campaignId, company_ids: companyIds, source }),
  })
}

export async function listContacts(
  options: {
    campaignId: string
    titleMatch?: boolean
    verificationStatus?: string
    stageFilter?: ContactStageFilter
    staleDays?: number
    search?: string
    limit?: number
    offset?: number
    sortBy?: string
    sortDir?: 'asc' | 'desc'
    letters?: string[]
    uploadId?: string
    countByLetters?: boolean
  },
): Promise<ContactListResponse> {
  const buildQuery = (sortBy: string | undefined, sortDir: 'asc' | 'desc' | undefined) => {
    const params = new URLSearchParams()
    params.set('campaign_id', options.campaignId)
    if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
    if (options.verificationStatus) params.set('verification_status', options.verificationStatus)
    if (options.stageFilter) params.set('stage_filter', options.stageFilter)
    if (options.staleDays) params.set('stale_days', String(options.staleDays))
    if (options.search) params.set('search', options.search)
    if (options.limit) params.set('limit', String(options.limit))
    if (options.offset) params.set('offset', String(options.offset))
    if (sortBy) params.set('sort_by', sortBy)
    if (sortDir) params.set('sort_dir', sortDir)
    if (options.letters && options.letters.length > 0) params.set('letters', options.letters.join(','))
    if (options.uploadId) params.set('upload_id', options.uploadId)
    if (options.countByLetters) params.set('count_by_letters', 'true')
    return params.toString()
  }

  const primarySortBy = options.sortBy
  const primarySortDir = options.sortDir
  const path = (sortBy: string | undefined, sortDir: 'asc' | 'desc' | undefined) =>
    `/v1/contacts?${buildQuery(sortBy, sortDir)}`

  contactsListLegacySortFallback = false
  try {
    return await request<ContactListResponse>(path(primarySortBy, primarySortDir))
  } catch (err) {
    const alreadyLegacy =
      primarySortBy === LEGACY_CONTACT_SORT.sortBy &&
      primarySortDir === LEGACY_CONTACT_SORT.sortDir
    const hadExplicitSort = Boolean(primarySortBy || primarySortDir)
    if (is422InvalidSortBy(err) && hadExplicitSort && !alreadyLegacy) {
      contactsListLegacySortFallback = true
      recordSortCompatFallback('contacts')
      return await request<ContactListResponse>(
        path(LEGACY_CONTACT_SORT.sortBy, LEGACY_CONTACT_SORT.sortDir),
      )
    }
    throw err
  }
}

export async function listCompanyContacts(
  campaignId: string,
  companyId: string,
  options: { limit?: number; offset?: number; titleMatch?: boolean; verificationStatus?: string; stageFilter?: ContactStageFilter } = {},
): Promise<ContactListResponse> {
  const params = new URLSearchParams()
  params.set('campaign_id', campaignId)
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.verificationStatus) params.set('verification_status', options.verificationStatus)
  if (options.stageFilter) params.set('stage_filter', options.stageFilter)
  return request<ContactListResponse>(`/v1/companies/${companyId}/contacts?${params.toString()}`)
}

export async function listContactCompanies(
  options: {
    campaignId: string
    search?: string
    limit?: number
    offset?: number
    titleMatch?: boolean
    verificationStatus?: string
    stageFilter?: ContactStageFilter
    matchGapFilter?: MatchGapFilter
    uploadId?: string
  },
): Promise<ContactCompanyListResponse> {
  const params = new URLSearchParams()
  params.set('campaign_id', options.campaignId)
  if (options.search) params.set('search', options.search)
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.verificationStatus) params.set('verification_status', options.verificationStatus)
  if (options.stageFilter) params.set('stage_filter', options.stageFilter)
  if (options.matchGapFilter) params.set('match_gap_filter', options.matchGapFilter)
  if (options.uploadId) params.set('upload_id', options.uploadId)
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  return request<ContactCompanyListResponse>(`/v1/contacts/companies?${params.toString()}`)
}

export function getContactsExportUrl(
  options: { campaignId: string; titleMatch?: boolean; verificationStatus?: string; stageFilter?: ContactStageFilter; companyId?: string; uploadId?: string },
): string {
  const params = new URLSearchParams()
  params.set('campaign_id', options.campaignId)
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.verificationStatus) params.set('verification_status', options.verificationStatus)
  if (options.stageFilter) params.set('stage_filter', options.stageFilter)
  if (options.companyId) params.set('company_id', options.companyId)
  if (options.uploadId) params.set('upload_id', options.uploadId)
  return `${API_BASE_URL}/v1/contacts/export.csv?${params.toString()}`
}

export async function getContactCounts(campaignId: string, uploadId?: string): Promise<ContactCountsResponse> {
  const params = new URLSearchParams()
  params.set('campaign_id', campaignId)
  if (uploadId) params.set('upload_id', uploadId)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<ContactCountsResponse>(`/v1/contacts/counts${suffix}`)
}

export async function verifyContacts(payload: ContactVerifyRequest, idempotencyKey?: string): Promise<ContactVerifyResult> {
  return request<ContactVerifyResult>('/v1/contacts/verify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(idempotencyKey ? { 'X-Idempotency-Key': idempotencyKey } : {}),
    },
    body: JSON.stringify(payload),
  })
}

export async function listTitleMatchRules(): Promise<TitleMatchRuleRead[]> {
  return request<TitleMatchRuleRead[]>('/v1/title-match-rules')
}

export async function createTitleMatchRule(payload: TitleMatchRuleCreate): Promise<TitleMatchRuleRead> {
  return request<TitleMatchRuleRead>('/v1/title-match-rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteTitleMatchRule(ruleId: string): Promise<void> {
  await request<void>(`/v1/title-match-rules/${ruleId}`, { method: 'DELETE' })
}

export async function seedTitleMatchRules(): Promise<TitleRuleSeedResult> {
  return request<TitleRuleSeedResult>('/v1/title-match-rules/seed', { method: 'POST' })
}

export async function testTitleMatch(title: string): Promise<TitleTestResult> {
  return request<TitleTestResult>('/v1/title-match-rules/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export async function getTitleRuleStats(): Promise<TitleRuleStatsResponse> {
  return request<TitleRuleStatsResponse>('/v1/title-match-rules/stats')
}

export async function previewTitleRuleImpact(
  campaignId: string,
  options: { source?: 'snov' | 'apollo' | 'both'; includeStale?: boolean; staleDays?: number; forceRefresh?: boolean } = {},
): Promise<TitleRuleImpactPreview> {
  const params = new URLSearchParams()
  params.set('campaign_id', campaignId)
  if (options.source) params.set('source', options.source)
  if (options.includeStale !== undefined) params.set('include_stale', String(options.includeStale))
  if (options.staleDays !== undefined) params.set('stale_days', String(options.staleDays))
  if (options.forceRefresh !== undefined) params.set('force_refresh', String(options.forceRefresh))
  return request<TitleRuleImpactPreview>(
    `/v1/title-match-rules/impact-preview?${params.toString()}`,
  )
}

export async function queueTitleRuleImpactFetch(
  campaignId: string,
  source: 'snov' | 'apollo' | 'both' = 'snov',
  options: { includeStale?: boolean; staleDays?: number; forceRefresh?: boolean } = {},
): Promise<ContactFetchResult> {
  const params = new URLSearchParams()
  params.set('campaign_id', campaignId)
  params.set('source', source)
  if (options.includeStale !== undefined) params.set('include_stale', String(options.includeStale))
  if (options.staleDays !== undefined) params.set('stale_days', String(options.staleDays))
  if (options.forceRefresh !== undefined) params.set('force_refresh', String(options.forceRefresh))
  return request<ContactFetchResult>(
    `/v1/title-match-rules/impact-fetch?${params.toString()}`,
    { method: 'POST' },
  )
}

export async function getIntegrationSettings(): Promise<IntegrationsStatusResponse> {
  return request<IntegrationsStatusResponse>('/v1/settings/integrations')
}

export async function updateIntegrationProvider(
  provider: IntegrationProviderId,
  payload: IntegrationProviderUpdateRequest,
): Promise<IntegrationProviderStatus> {
  return request<IntegrationProviderStatus>(`/v1/settings/integrations/${encodeURIComponent(provider)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function testIntegrationProvider(
  provider: IntegrationProviderId,
): Promise<IntegrationTestResponse> {
  return request<IntegrationTestResponse>(`/v1/settings/integrations/${encodeURIComponent(provider)}/test`, {
    method: 'POST',
  })
}

export async function loginWithPassword(email: string, password: string): Promise<AuthLoginResponse> {
  return request<AuthLoginResponse>('/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

export async function getCurrentUser(): Promise<AuthUserRead> {
  return request<AuthUserRead>('/v1/auth/me')
}

export async function logoutSession(): Promise<void> {
  await request<void>('/v1/auth/logout', { method: 'POST' })
}

/** Parse a date string as UTC.
 * The API returns TIMESTAMP WITHOUT TIME ZONE values without a 'Z' suffix.
 * Bare ISO strings (no Z / offset) are treated as local time by browsers,
 * so we force UTC by appending 'Z' when no timezone info is present.
 */
export function parseUTC(dateStr: string): Date {
  const s =
    dateStr.endsWith('Z') || dateStr.includes('+') || /[+-]\d{2}:\d{2}$/.test(dateStr)
      ? dateStr
      : dateStr + 'Z'
  return new Date(s)
}
