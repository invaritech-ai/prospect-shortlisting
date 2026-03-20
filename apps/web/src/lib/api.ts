import type {
  AnalysisJobDetailRead,
  AnalysisRunJobRead,
  CompanyCounts,
  CompanyDeleteResult,
  CompanyIdsResult,
  CompanyList,
  CompanyScrapeResult,
  ContactFetchResult,
  ContactListResponse,
  DecisionFilter,
  DrainQueueResult,
  FeedbackRead,
  FeedbackUpsert,
  JobEnqueueResult,
  LetterCounts,
  PromptCreate,
  PromptRead,
  PromptUpdate,
  ResetStuckResult,
  RunCreateRequest,
  RunCreateResult,
  RunRead,
  ScrapeFilter,
  ScrapeJobCreate,
  ScrapeJobRead,
  ScrapePageContentRead,
  StatsResponse,
  TitleMatchRuleCreate,
  TitleMatchRuleRead,
  TitleRuleSeedResult,
  UploadCompanyList,
  UploadCreateResult,
  UploadDetail,
  UploadList,
} from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
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
  const form = new FormData()
  form.append('file', file)
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

export async function listCompanies(
  limit = 25,
  offset = 0,
  decisionFilter: DecisionFilter = 'all',
  includeTotal = false,
  scrapeFilter: ScrapeFilter = 'all',
  letter: string | null = null,
): Promise<CompanyList> {
  let url = `/v1/companies?limit=${limit}&offset=${offset}&decision_filter=${encodeURIComponent(decisionFilter)}&scrape_filter=${encodeURIComponent(scrapeFilter)}&include_total=${includeTotal}`
  if (letter) url += `&letter=${encodeURIComponent(letter)}`
  return request<CompanyList>(url)
}

export async function deleteCompanies(companyIds: string[]): Promise<CompanyDeleteResult> {
  return request<CompanyDeleteResult>('/v1/companies/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_ids: companyIds }),
  })
}

export async function scrapeSelectedCompanies(companyIds: string[]): Promise<CompanyScrapeResult> {
  return request<CompanyScrapeResult>('/v1/companies/scrape-selected', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_ids: companyIds }),
  })
}

export async function scrapeAllCompanies(): Promise<CompanyScrapeResult> {
  return request<CompanyScrapeResult>('/v1/companies/scrape-all', {
    method: 'POST',
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

export async function enqueueRunAll(jobId: string): Promise<JobEnqueueResult> {
  return request<JobEnqueueResult>(`/v1/scrape-jobs/${jobId}/enqueue-run-all`, {
    method: 'POST',
  })
}

export async function getScrapeJob(jobId: string): Promise<ScrapeJobRead> {
  return request<ScrapeJobRead>(`/v1/scrape-jobs/${jobId}`)
}

export async function listScrapeJobs(limit = 50, offset = 0, statusFilter: ScrapeJobFilter = 'all'): Promise<ScrapeJobRead[]> {
  return request<ScrapeJobRead[]>(
    `/v1/scrape-jobs?limit=${limit}&offset=${offset}&status_filter=${encodeURIComponent(statusFilter)}`,
  )
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

export async function getStats(): Promise<StatsResponse> {
  return request<StatsResponse>('/v1/stats')
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
  letter: string | null = null,
): Promise<CompanyIdsResult> {
  let url = `/v1/companies/ids?decision_filter=${encodeURIComponent(decisionFilter)}&scrape_filter=${encodeURIComponent(scrapeFilter)}`
  if (letter) url += `&letter=${encodeURIComponent(letter)}`
  return request<CompanyIdsResult>(url)
}

export async function getLetterCounts(
  decisionFilter: DecisionFilter = 'all',
  scrapeFilter: ScrapeFilter = 'all',
): Promise<LetterCounts> {
  return request<LetterCounts>(
    `/v1/companies/letter-counts?decision_filter=${encodeURIComponent(decisionFilter)}&scrape_filter=${encodeURIComponent(scrapeFilter)}`,
  )
}

// ── Contacts ──────────────────────────────────────────────────────────────────

export async function fetchContactsForCompany(companyId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/companies/${companyId}/fetch-contacts`, { method: 'POST' })
}

export async function fetchContactsForRun(runId: string): Promise<ContactFetchResult> {
  return request<ContactFetchResult>(`/v1/runs/${runId}/fetch-contacts`, { method: 'POST' })
}

export async function listContacts(
  options: {
    titleMatch?: boolean
    emailStatus?: string
    search?: string
    limit?: number
    offset?: number
  } = {},
): Promise<ContactListResponse> {
  const params = new URLSearchParams()
  if (options.titleMatch !== undefined) params.set('title_match', String(options.titleMatch))
  if (options.emailStatus) params.set('email_status', options.emailStatus)
  if (options.search) params.set('search', options.search)
  if (options.limit) params.set('limit', String(options.limit))
  if (options.offset) params.set('offset', String(options.offset))
  return request<ContactListResponse>(`/v1/contacts?${params.toString()}`)
}

export async function listCompanyContacts(companyId: string): Promise<ContactListResponse> {
  return request<ContactListResponse>(`/v1/companies/${companyId}/contacts`)
}

export function getContactsExportUrl(titleMatch?: boolean, emailStatus?: string): string {
  const params = new URLSearchParams()
  if (titleMatch !== undefined) params.set('title_match', String(titleMatch))
  if (emailStatus) params.set('email_status', emailStatus)
  return `${API_BASE_URL}/v1/contacts/export.csv?${params.toString()}`
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
