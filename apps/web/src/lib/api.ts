import type {
  CompanyDeleteResult,
  CompanyList,
  DecisionFilter,
  JobEnqueueResult,
  ScrapeJobCreate,
  ScrapeJobRead,
  UploadCompanyList,
  UploadCreateResult,
  UploadDetail,
  UploadList,
} from './types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')

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
): Promise<CompanyList> {
  return request<CompanyList>(
    `/v1/companies?limit=${limit}&offset=${offset}&decision_filter=${encodeURIComponent(decisionFilter)}`,
  )
}

export async function deleteCompanies(companyIds: string[]): Promise<CompanyDeleteResult> {
  return request<CompanyDeleteResult>('/v1/companies/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company_ids: companyIds }),
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
