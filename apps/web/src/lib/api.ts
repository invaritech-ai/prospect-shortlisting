import type {
  AnalysisJobDetailRead,
  AnalysisRunJobRead,
  CompanyDeleteResult,
  CompanyList,
  CompanyScrapeResult,
  DecisionFilter,
  DrainQueueResult,
  JobEnqueueResult,
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
): Promise<CompanyList> {
  return request<CompanyList>(
    `/v1/companies?limit=${limit}&offset=${offset}&decision_filter=${encodeURIComponent(decisionFilter)}&scrape_filter=${encodeURIComponent(scrapeFilter)}&include_total=${includeTotal}`,
  )
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

export function getCompaniesExportUrl(): string {
  return `${API_BASE_URL}/v1/companies/export.csv`
}
