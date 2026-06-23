import type {
  AiReviewDomainAnalysis,
  AiReviewDomainList,
  AiReviewJobCreate,
  AiReviewJobRead,
  AiReviewJobStatusRead,
  AiReviewLabelCounts,
  CampaignCreate,
  CampaignList,
  CampaignRead,
  CampaignStageCounts,
  ContactList,
  DecisionSettingsCreate,
  DecisionSettingsList,
  DecisionSettingsRead,
  DecisionSettingsUpdate,
  DomainList,
  DomainLetterCounts,
  EmailFetchBatchCreate,
  EmailFetchBatchRead,
  EmailFetchCompanyIds,
  EmailFetchCompanyList,
  EmailFetchCompanyStatus,
  EmailFetchCriteriaRead,
  EmailFetchCriteriaSaveRequest,
  EmailFetchPreviewRead,
  EmailFetchPreviewRequest,
  EmailVerificationBatchCreate,
  EmailVerificationBatchRead,
  EmailVerificationContactIds,
  EmailVerificationContactList,
  EmailVerificationPreviewRead,
  EmailVerificationPreviewRequest,
  EmailVerificationStatus,
  FetchedPersonList,
  FullPipelineCompanyList,
  IntegrationHealthItem,
  IntegrationProviderId,
  IntegrationProviderStatus,
  IntegrationProviderUpdateRequest,
  IntegrationTestResponse,
  IntegrationsStatusResponse,
  PipelineCostSummaryRead,
  ScrapeBatchCreate,
  ScrapeBatchRead,
  ScrapeJobStatusRead,
  ScrapeResultRead,
  ScrapeSettingsList,
  ScrapeSettingsRead,
  UploadCreateResult,
  UploadList,
} from './types'

const viteEnv = (import.meta as { env?: Record<string, string | undefined> }).env
const API_BASE_URL = (
  viteEnv?.VITE_API_BASE_URL ??
  (globalThis as { __API_BASE_URL__?: string }).__API_BASE_URL__ ??
  'http://localhost:8000'
).replace(/\/+$/, '')

export function buildApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalized}`
}

interface ApiSessionConfig {
  getAccessToken?: () => string | null
  onUnauthorized?: () => void
}

interface AuthUserRead {
  email: string
  display_name?: string | null
}

interface AuthLoginResponse {
  user: AuthUserRead
  access_token?: string | null
  token_type?: string | null
}

type SortDir = 'asc' | 'desc'
type ListQueryOptions<TStatus extends string = string> = {
  status?: 'all' | TStatus
  letter?: string
  search?: string
  sortBy?: string
  sortDir?: SortDir
  limit?: number
  offset?: number
}
type IdListQueryOptions<TStatus extends string = string> = Omit<ListQueryOptions<TStatus>, 'sortBy' | 'sortDir'> & {
  fetchableOnly?: boolean
  actionableOnly?: boolean
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = apiSessionConfig.getAccessToken?.() ?? null
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(buildApiUrl(path), {
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

function jsonRequest<T>(path: string, method: 'POST' | 'PUT', body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

async function requestBlob(path: string, init?: RequestInit): Promise<{ blob: Blob; filename: string | null }> {
  const token = apiSessionConfig.getAccessToken?.() ?? null
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(buildApiUrl(path), {
    ...init,
    headers,
    credentials: init?.credentials ?? 'include',
  })
  if (!response.ok) {
    if (response.status === 401) apiSessionConfig.onUnauthorized?.()
    const contentType = response.headers.get('content-type') ?? ''
    const body = contentType.includes('application/json') ? await response.json() : await response.text()
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? (body as { detail: unknown }).detail
        : body
    throw new ApiError(response.status, detail)
  }
  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get('content-disposition')),
  }
}

function campaignParams(campaignId: string, limit?: number, offset?: number): URLSearchParams {
  const params = new URLSearchParams({ campaign_id: campaignId })
  if (limit !== undefined) params.set('limit', String(limit))
  if (offset !== undefined) params.set('offset', String(offset))
  return params
}

function setTrimmedParam(params: URLSearchParams, key: string, value?: string): void {
  const trimmed = value?.trim()
  if (trimmed) params.set(key, trimmed)
}

function applyListQueryParams(params: URLSearchParams, options: ListQueryOptions): void {
  if (options.status) params.set('status', options.status)
  if (options.letter) params.set('letter', options.letter)
  setTrimmedParam(params, 'search', options.search)
  if (options.sortBy) params.set('sort_by', options.sortBy)
  if (options.sortDir) params.set('sort_dir', options.sortDir)
}

function filenameFromContentDisposition(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null
  const encoded = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encoded?.[1]) return decodeURIComponent(encoded[1])
  const plain = contentDisposition.match(/filename="?([^";]+)"?/i)
  return plain?.[1] ?? null
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  if (typeof document === 'undefined') {
    throw new Error('File downloads require a browser environment.')
  }
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function loginWithPassword(email: string, password: string): Promise<AuthLoginResponse> {
  return jsonRequest<AuthLoginResponse>('/v1/auth/login', 'POST', { email, password })
}

export async function getCurrentUser(): Promise<AuthUserRead> {
  return request<AuthUserRead>('/v1/auth/me')
}

export async function logoutSession(): Promise<void> {
  await request<void>('/v1/auth/logout', { method: 'POST' })
}

// ── Campaigns ─────────────────────────────────────────────────────────────────

export async function listCampaigns(limit = 50, offset = 0): Promise<CampaignList> {
  return request<CampaignList>(`/v1/campaigns?limit=${limit}&offset=${offset}`)
}

export async function createCampaign(payload: CampaignCreate): Promise<CampaignRead> {
  return jsonRequest<CampaignRead>('/v1/campaigns', 'POST', payload)
}

export async function deleteCampaign(campaignId: string): Promise<void> {
  await request<void>(`/v1/campaigns/${campaignId}`, { method: 'DELETE' })
}

export async function getCampaignCosts(campaignId: string): Promise<PipelineCostSummaryRead> {
  return request<PipelineCostSummaryRead>(`/v1/campaigns/${encodeURIComponent(campaignId)}/costs`)
}

export async function getCampaignStageCounts(campaignId: string): Promise<CampaignStageCounts> {
  return request<CampaignStageCounts>(`/v1/campaigns/${encodeURIComponent(campaignId)}/stage-counts`)
}

// ── Uploads ───────────────────────────────────────────────────────────────────

export async function uploadFileToCampaign(file: File, campaignId: string): Promise<UploadCreateResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('campaign_id', campaignId)
  return request<UploadCreateResult>('/v1/uploads', { method: 'POST', body: form })
}

export async function listUploads(campaignId: string, limit = 50, offset = 0): Promise<UploadList> {
  return request<UploadList>(`/v1/uploads?${campaignParams(campaignId, limit, offset).toString()}`)
}

// ── Domains ───────────────────────────────────────────────────────────────────

export async function listDomains(
  campaignId: string,
  {
    uploadId,
    scrapeStatus,
    letter,
    search,
    sortBy,
    sortDir,
    limit = 50,
    offset = 0,
  }: {
    uploadId?: string
    scrapeStatus?: string
    letter?: string
    label?: string
    search?: string
    sortBy?: string
    sortDir?: 'asc' | 'desc'
    limit?: number
    offset?: number
  } = {},
): Promise<DomainList> {
  const params = campaignParams(campaignId, limit, offset)
  if (uploadId) params.set('upload_id', uploadId)
  if (scrapeStatus) params.set('scrape_status', scrapeStatus)
  applyListQueryParams(params, { letter, search, sortBy, sortDir })
  return request<DomainList>(`/v1/companies?${params.toString()}`)
}

export async function listFullPipelineCompanies(
  campaignId: string,
  {
    search,
    limit = 50,
    offset = 0,
  }: {
    search?: string
    limit?: number
    offset?: number
  } = {},
): Promise<FullPipelineCompanyList> {
  const params = campaignParams(campaignId, limit, offset)
  setTrimmedParam(params, 'search', search)
  return request<FullPipelineCompanyList>(`/v1/full-pipeline/companies?${params.toString()}`)
}

export async function listAiReviewDomains(
  campaignId: string,
  {
    letter,
    label,
    search,
    sortBy,
    sortDir,
    limit = 50,
    offset = 0,
  }: {
    letter?: string
    label?: string
    search?: string
    sortBy?: string
    sortDir?: 'asc' | 'desc'
    limit?: number
    offset?: number
  } = {},
): Promise<AiReviewDomainList> {
  const params = campaignParams(campaignId, limit, offset)
  if (label) params.set('label', label)
  applyListQueryParams(params, { letter, search, sortBy, sortDir })
  return request<AiReviewDomainList>(`/v1/ai-review/domains?${params.toString()}`)
}

export async function getAiReviewDomainAnalysis(
  campaignId: string,
  domainId: string,
): Promise<AiReviewDomainAnalysis> {
  return request<AiReviewDomainAnalysis>(
    `/v1/ai-review/domains/${encodeURIComponent(domainId)}/analysis?campaign_id=${encodeURIComponent(campaignId)}`,
  )
}

export async function getAiReviewLetterCounts(campaignId: string): Promise<DomainLetterCounts> {
  return request<DomainLetterCounts>(`/v1/ai-review/letter-counts?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function getAiReviewLabelCounts(
  campaignId: string,
  { letter, search }: { letter?: string; search?: string } = {},
): Promise<AiReviewLabelCounts> {
  const params = campaignParams(campaignId)
  applyListQueryParams(params, { letter, search })
  return request<AiReviewLabelCounts>(`/v1/ai-review/label-counts?${params.toString()}`)
}

export async function createAiReviewJob(body: AiReviewJobCreate): Promise<AiReviewJobRead> {
  return jsonRequest<AiReviewJobRead>('/v1/ai-review/jobs', 'POST', body)
}

export async function getActiveAiReviewJob(campaignId: string): Promise<AiReviewJobRead | null> {
  return request<AiReviewJobRead | null>(`/v1/ai-review/jobs/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function getAiReviewJobStatus(batchId: string): Promise<AiReviewJobStatusRead> {
  return request<AiReviewJobStatusRead>(`/v1/ai-review/jobs/${encodeURIComponent(batchId)}/status`)
}

export async function getDomainLetterCounts(
  campaignId: string,
  scrapeStatus?: string,
): Promise<DomainLetterCounts> {
  const params = campaignParams(campaignId)
  if (scrapeStatus) params.set('scrape_status', scrapeStatus)
  return request<DomainLetterCounts>(`/v1/domains/letter-counts?${params.toString()}`)
}

// ── S3 Email Fetch ───────────────────────────────────────────────────────────

export async function getEmailFetchCriteria(campaignId: string): Promise<EmailFetchCriteriaRead> {
  return request<EmailFetchCriteriaRead>(`/v1/email-fetch/criteria?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function saveEmailFetchCriteria(payload: EmailFetchCriteriaSaveRequest): Promise<EmailFetchCriteriaRead> {
  return jsonRequest<EmailFetchCriteriaRead>('/v1/email-fetch/criteria', 'POST', payload)
}

export async function listEmailFetchCompanies(
  campaignId: string,
  options: ListQueryOptions<EmailFetchCompanyStatus> = {},
): Promise<EmailFetchCompanyList> {
  const { limit = 200, offset = 0 } = options
  const params = campaignParams(campaignId, limit, offset)
  applyListQueryParams(params, options)
  return request<EmailFetchCompanyList>(`/v1/email-fetch/companies?${params.toString()}`)
}

export async function getEmailFetchLetterCounts(
  campaignId: string,
  {
    status,
    search,
  }: {
    status?: 'all' | EmailFetchCompanyStatus
    search?: string
  } = {},
): Promise<DomainLetterCounts> {
  const params = campaignParams(campaignId)
  applyListQueryParams(params, { status, search })
  return request<DomainLetterCounts>(`/v1/email-fetch/letter-counts?${params.toString()}`)
}

export async function listEmailFetchCompanyIds(
  campaignId: string,
  options: IdListQueryOptions<EmailFetchCompanyStatus> = {},
): Promise<EmailFetchCompanyIds> {
  const { fetchableOnly = false, limit = 200, offset = 0 } = options
  const params = campaignParams(campaignId, limit, offset)
  applyListQueryParams(params, options)
  if (fetchableOnly) params.set('fetchable_only', 'true')
  return request<EmailFetchCompanyIds>(`/v1/email-fetch/company-ids?${params.toString()}`)
}

export async function previewEmailFetch(body: EmailFetchPreviewRequest): Promise<EmailFetchPreviewRead> {
  return jsonRequest<EmailFetchPreviewRead>('/v1/email-fetch/preview', 'POST', body)
}

export async function createEmailFetchBatch(body: EmailFetchBatchCreate): Promise<EmailFetchBatchRead> {
  return jsonRequest<EmailFetchBatchRead>('/v1/email-fetch/batches', 'POST', body)
}

export async function getActiveEmailFetchBatch(campaignId: string): Promise<EmailFetchBatchRead | null> {
  return request<EmailFetchBatchRead | null>(`/v1/email-fetch/batches/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

// ── S4 Email Verification ───────────────────────────────────────────────────

export async function listEmailVerificationContacts(
  campaignId: string,
  options: ListQueryOptions<EmailVerificationStatus> = {},
): Promise<EmailVerificationContactList> {
  const { limit = 50, offset = 0 } = options
  const params = campaignParams(campaignId, limit, offset)
  applyListQueryParams(params, options)
  return request<EmailVerificationContactList>(`/v1/email-verification/contacts?${params.toString()}`)
}

export async function listEmailVerificationContactIds(
  campaignId: string,
  options: IdListQueryOptions<EmailVerificationStatus> = {},
): Promise<EmailVerificationContactIds> {
  const { actionableOnly = false, limit = 200, offset = 0 } = options
  const params = campaignParams(campaignId, limit, offset)
  applyListQueryParams(params, options)
  if (actionableOnly) params.set('actionable_only', 'true')
  return request<EmailVerificationContactIds>(`/v1/email-verification/contact-ids?${params.toString()}`)
}

export async function getEmailVerificationLetterCounts(
  campaignId: string,
  {
    status,
    search,
  }: {
    status?: 'all' | EmailVerificationStatus
    search?: string
  } = {},
): Promise<DomainLetterCounts> {
  const params = campaignParams(campaignId)
  applyListQueryParams(params, { status, search })
  return request<DomainLetterCounts>(`/v1/email-verification/letter-counts?${params.toString()}`)
}

export async function previewEmailVerification(body: EmailVerificationPreviewRequest): Promise<EmailVerificationPreviewRead> {
  return jsonRequest<EmailVerificationPreviewRead>('/v1/email-verification/preview', 'POST', body)
}

export async function createEmailVerificationBatch(body: EmailVerificationBatchCreate): Promise<EmailVerificationBatchRead> {
  return jsonRequest<EmailVerificationBatchRead>('/v1/email-verification/batches', 'POST', body)
}

export async function getActiveEmailVerificationBatch(campaignId: string): Promise<EmailVerificationBatchRead | null> {
  return request<EmailVerificationBatchRead | null>(`/v1/email-verification/batches/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function downloadFreshValidEmailCsv(campaignId: string): Promise<void> {
  const params = campaignParams(campaignId)
  const { blob, filename } = await requestBlob(`/v1/email-verification/exports/valid.csv?${params.toString()}`)
  triggerBrowserDownload(blob, filename ?? `valid-emails-${campaignId}.csv`)
}

export async function listContacts(
  campaignId: string,
  {
    domainId,
    hasEmail,
    limit = 200,
    offset = 0,
  }: {
    domainId?: string
    hasEmail?: boolean
    limit?: number
    offset?: number
  } = {},
): Promise<ContactList> {
  const params = campaignParams(campaignId, limit, offset)
  if (domainId) params.set('domain_id', domainId)
  if (typeof hasEmail === 'boolean') params.set('has_email', String(hasEmail))
  return request<ContactList>(`/v1/contacts?${params.toString()}`)
}

export async function listFetchedPeople(
  campaignId: string,
  {
    domainId,
    status,
    limit = 200,
    offset = 0,
  }: {
    domainId?: string
    status?: string
    limit?: number
    offset?: number
  } = {},
): Promise<FetchedPersonList> {
  const params = campaignParams(campaignId, limit, offset)
  if (domainId) params.set('domain_id', domainId)
  if (status) params.set('status', status)
  return request<FetchedPersonList>(`/v1/fetched-people?${params.toString()}`)
}

// ── S1 Scrape Batches ─────────────────────────────────────────────────────────

export async function createScrapeJob(body: ScrapeBatchCreate): Promise<ScrapeBatchRead> {
  return jsonRequest<ScrapeBatchRead>('/v1/scrape-jobs', 'POST', body)
}

export async function getActiveBatch(campaignId: string): Promise<ScrapeBatchRead | null> {
  return request<ScrapeBatchRead | null>(`/v1/scrape-batches/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function getScrapeJobStatus(batchId: string): Promise<ScrapeJobStatusRead> {
  return request<ScrapeJobStatusRead>(`/v1/scrape-jobs/${encodeURIComponent(batchId)}/status`)
}

// ── S1 Scrape Settings ────────────────────────────────────────────────────────

export async function listScrapeSettings(campaignId: string, limit = 20): Promise<ScrapeSettingsList> {
  return request<ScrapeSettingsList>(`/v1/scrape-settings/history?${campaignParams(campaignId, limit).toString()}`)
}

export async function saveScrapeSettings(campaignId: string, instructionText: string): Promise<ScrapeSettingsRead> {
  return jsonRequest<ScrapeSettingsRead>('/v1/scrape-settings', 'POST', {
    campaign_id: campaignId,
    instruction_text: instructionText,
  })
}

// ── S2 Decision Settings ──────────────────────────────────────────────────────

export async function listDecisionSettings(
  campaignId: string,
  { limit = 50, offset = 0, isActive }: { limit?: number; offset?: number; isActive?: boolean } = {},
): Promise<DecisionSettingsList> {
  const params = campaignParams(campaignId, limit, offset)
  if (typeof isActive === 'boolean') params.set('is_active', String(isActive))
  return request<DecisionSettingsList>(`/v1/decision-settings?${params.toString()}`)
}

export async function createDecisionSettings(payload: DecisionSettingsCreate): Promise<DecisionSettingsRead> {
  return jsonRequest<DecisionSettingsRead>('/v1/decision-settings', 'POST', payload)
}

export async function updateDecisionSettings(settingsId: string, payload: DecisionSettingsUpdate): Promise<DecisionSettingsRead> {
  return jsonRequest<DecisionSettingsRead>(`/v1/decision-settings/${encodeURIComponent(settingsId)}`, 'PUT', payload)
}

export async function deleteDecisionSettings(settingsId: string): Promise<void> {
  await request<void>(`/v1/decision-settings/${encodeURIComponent(settingsId)}`, { method: 'DELETE' })
}

// ── S1 Scrape Results (content drawer) ───────────────────────────────────────

export async function getScrapeResult(domainId: string, campaignId: string): Promise<ScrapeResultRead | null> {
  const params = campaignParams(campaignId)
  params.set('domain_id', domainId)
  return request<ScrapeResultRead | null>(`/v1/scrape-results?${params.toString()}`).catch(() => null)
}

// ── Settings / Integrations ───────────────────────────────────────────────────

export async function getIntegrationSettings(): Promise<IntegrationsStatusResponse> {
  return request<IntegrationsStatusResponse>('/v1/settings/integrations')
}

export async function updateIntegrationProvider(
  provider: IntegrationProviderId,
  payload: IntegrationProviderUpdateRequest,
): Promise<IntegrationProviderStatus> {
  return jsonRequest<IntegrationProviderStatus>(
    `/v1/settings/integrations/${encodeURIComponent(provider)}`,
    'PUT',
    payload,
  )
}

export async function testIntegrationProvider(provider: IntegrationProviderId): Promise<IntegrationTestResponse> {
  return request<IntegrationTestResponse>(`/v1/settings/integrations/${encodeURIComponent(provider)}/test`, { method: 'POST' })
}

export async function getIntegrationsHealth(): Promise<IntegrationHealthItem[]> {
  return request<IntegrationHealthItem[]>('/v1/settings/integrations/health')
}
