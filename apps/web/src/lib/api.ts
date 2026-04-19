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

  LetterCounts,
  PromptCreate,
  PromptRead,
  PromptUpdate,
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
  TitleRuleSeedResult,
  TitleTestResult,
  TitleRuleStatsResponse,
  UploadCompanyList,
  UploadCreateResult,
  UploadDetail,
  UploadList,
  MatchGapFilter,
} from './types'

const viteEnv = (import.meta as { env?: Record<string, string | undefined> }).env
const API_BASE_URL = (
  viteEnv?.VITE_API_BASE_URL ??
  (globalThis as { __API_BASE_URL__?: string }).__API_BASE_URL__ ??
  'http://localhost:8000'
).replace(/\/+$/, '')
type ScrapeJobFilter = 'all' | 'active' | 'completed' | 'failed'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(`API error ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (response.status === 204) {
    if (!response.ok) throw new ApiError(response.status, null)
    return undefined as T
  }
  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
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
  limit = 25,
  offset = 0,
  decisionFilter: DecisionFilter = 'all',
  includeTotal = false,
  scrapeFilter: ScrapeFilter = 'all',
  stageFilter: CompanyStageFilter = 'all',
  letter: string | null = null,
  sortBy = 'domain',
  sortDir: 'asc' | 'desc' = 'asc',
  uploadId?: string,
  letters?: string[],
): Promise<CompanyList> {
  let url = `/v1/companies?limit=${limit}&offset=${offset}&decision_filter=${encodeURIComponent(decisionFilter)}&scrape_filter=${encodeURIComponent(scrapeFilter)}&stage_filter=${encodeURIComponent(stageFilter)}&include_total=${includeTotal}&sort_by=${encodeURIComponent(sortBy)}&sort_dir=${sortDir}`
  if (letter) url += `&letter=${encodeURIComponent(letter)}`
  if (letters && letters.length > 0) url += `&letters=${encodeURIComponent(letters.join(','))}`
  if (uploadId) url += `&upload_id=${encodeURIComponent(uploadId)}`
  return request<CompanyList>(url)
}

export async function deleteCompanies(companyIds: string[]): Promise<CompanyDeleteResult> {
  return request<CompanyDeleteResult>('/v1/companies/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_ids: companyIds }),
  })
}

export async function scrapeSelectedCompanies(
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

export async function listRuns(limit = 25, offset = 0): Promise<RunRead[]> {
  return request<RunRead[]>(`/v1/runs?limit=${limit}&offset=${offset}`)
}

export async function listRunJobs(runId: string, limit = 500, offset = 0): Promise<AnalysisRunJobRead[]> {
  return request<AnalysisRunJobRead[]>(`/v1/runs/${runId}/jobs?limit=${limit}&offset=${offset}`)
}

export async function getAnalysisJobDetail(analysisJobId: string): Promise<AnalysisJobDetailRead> {
  return request<AnalysisJobDetailRead>(`/v1/analysis-jobs/${analysisJobId}`)
}

export async function getStats(uploadId?: string): Promise<StatsResponse> {
  const params = new URLSearchParams()
  if (uploadId) params.set('upload_id', uploadId)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<StatsResponse>(`/v1/stats${suffix}`)
}

export async function getCostStats(
  options: { windowDays?: number; uploadId?: string; limit?: number; offset?: number } = {},
): Promise<CostStatsResponse> {
  const params = new URLSearchParams()
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

export async function getCompanyCounts(): Promise<CompanyCounts> {
  return request<CompanyCounts>('/v1/companies/counts')
}

export function getCompaniesExportUrl(): string {
  return `${API_BASE_URL}/v1/companies/export.csv`
}

export async function upsertCompanyFeedback(companyId: string, payload: FeedbackUpsert): Promise<FeedbackRead> {
  return request<FeedbackRead>(`/v1/companies/${companyId}/feedback`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listCompanyIds(
  decisionFilter: DecisionFilter = 'all',
  scrapeFilter: ScrapeFilter = 'all',
  stageFilter: CompanyStageFilter = 'all',
  letter: string | null = null,
  uploadId?: string,
  letters?: string[],
): Promise<CompanyIdsResult> {
  let url = `/v1/companies/ids?decision_filter=${encodeURIComponent(decisionFilter)}&scrape_filter=${encodeURIComponent(scrapeFilter)}&stage_filter=${encodeURIComponent(stageFilter)}`
  if (letter) url += `&letter=${encodeURIComponent(letter)}`
  if (letters && letters.length > 0) url += `&letters=${encodeURIComponent(letters.join(','))}`
  if (uploadId) url += `&upload_id=${encodeURIComponent(uploadId)}`
  return request<CompanyIdsResult>(url)
}

export async function getLetterCounts(
  decisionFilter: DecisionFilter = 'all',
  scrapeFilter: ScrapeFilter = 'all',
  stageFilter: CompanyStageFilter = 'all',
  uploadId?: string,
): Promise<LetterCounts> {
  const uploadParam = uploadId ? `&upload_id=${encodeURIComponent(uploadId)}` : ''
  return request<LetterCounts>(
    `/v1/companies/letter-counts?decision_filter=${encodeURIComponent(decisionFilter)}&scrape_filter=${encodeURIComponent(scrapeFilter)}&stage_filter=${encodeURIComponent(stageFilter)}${uploadParam}`,
  )
}

// ── Contacts ──────────────────────────────────────────────────────────────────

export async function fetchContactsForCompany(companyId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/companies/${companyId}/fetch-contacts`, { method: 'POST' })
}

export async function fetchContactsForRun(runId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/runs/${runId}/fetch-contacts`, { method: 'POST' })
}

export async function fetchContactsForCompanyApollo(companyId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/companies/${companyId}/fetch-contacts/apollo`, { method: 'POST' })
}

export async function fetchContactsForRunApollo(runId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/runs/${runId}/fetch-contacts/apollo`, { method: 'POST' })
}

export async function fetchContactsSelected(
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
    body: JSON.stringify({ company_ids: companyIds, source }),
  })
}

export async function listContacts(
  options: {
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
  } = {},
): Promise<ContactListResponse> {
  const params = new URLSearchParams()
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.verificationStatus) params.set('verification_status', options.verificationStatus)
  if (options.stageFilter) params.set('stage_filter', options.stageFilter)
  if (options.staleDays) params.set('stale_days', String(options.staleDays))
  if (options.search) params.set('search', options.search)
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  if (options.sortBy) params.set('sort_by', options.sortBy)
  if (options.sortDir) params.set('sort_dir', options.sortDir)
  if (options.letters && options.letters.length > 0) params.set('letters', options.letters.join(','))
  if (options.uploadId) params.set('upload_id', options.uploadId)
  if (options.countByLetters) params.set('count_by_letters', 'true')
  return request<ContactListResponse>(`/v1/contacts?${params.toString()}`)
}

export async function listCompanyContacts(
  companyId: string,
  options: { limit?: number; offset?: number; titleMatch?: boolean; verificationStatus?: string; stageFilter?: ContactStageFilter } = {},
): Promise<ContactListResponse> {
  const params = new URLSearchParams()
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.verificationStatus) params.set('verification_status', options.verificationStatus)
  if (options.stageFilter) params.set('stage_filter', options.stageFilter)
  return request<ContactListResponse>(`/v1/companies/${companyId}/contacts?${params.toString()}`)
}

export async function listContactCompanies(
  options: {
    search?: string
    limit?: number
    offset?: number
    titleMatch?: boolean
    verificationStatus?: string
    stageFilter?: ContactStageFilter
    matchGapFilter?: MatchGapFilter
    uploadId?: string
  } = {},
): Promise<ContactCompanyListResponse> {
  const params = new URLSearchParams()
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
  options: { titleMatch?: boolean; verificationStatus?: string; stageFilter?: ContactStageFilter; companyId?: string; uploadId?: string } = {},
): string {
  const params = new URLSearchParams()
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.verificationStatus) params.set('verification_status', options.verificationStatus)
  if (options.stageFilter) params.set('stage_filter', options.stageFilter)
  if (options.companyId) params.set('company_id', options.companyId)
  if (options.uploadId) params.set('upload_id', options.uploadId)
  return `${API_BASE_URL}/v1/contacts/export.csv?${params.toString()}`
}

export async function getContactCounts(uploadId?: string): Promise<ContactCountsResponse> {
  const params = new URLSearchParams()
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
