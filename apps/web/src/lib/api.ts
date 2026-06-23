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
  DomainScrapeCounts,
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
  ScrapeBatchList,
  ScrapeBatchRead,
  ScrapeJobStatusRead,
  ScrapeResultRead,
  ScrapeSettingsList,
  ScrapeSettingsRead,
  ScrapeSettingsUpdate,
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

// ── Campaigns ─────────────────────────────────────────────────────────────────

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
  return request<UploadList>(`/v1/uploads?campaign_id=${encodeURIComponent(campaignId)}&limit=${limit}&offset=${offset}`)
}

export async function deleteUpload(uploadId: string): Promise<void> {
  return request<void>(`/v1/uploads/${uploadId}`, { method: 'DELETE' })
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
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (uploadId) params.set('upload_id', uploadId)
  if (scrapeStatus) params.set('scrape_status', scrapeStatus)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  if (sortBy) params.set('sort_by', sortBy)
  if (sortDir) params.set('sort_dir', sortDir)
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
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (search?.trim()) params.set('search', search.trim())
  return request<FullPipelineCompanyList>(`/v1/full-pipeline/companies?${params.toString()}`)
}

export async function listAiDecidableDomains(
  campaignId: string,
  {
    uploadId,
    letter,
    search,
    limit = 50,
    offset = 0,
  }: {
    uploadId?: string
    letter?: string
    search?: string
    limit?: number
    offset?: number
  } = {},
): Promise<DomainList> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (uploadId) params.set('upload_id', uploadId)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  return request<DomainList>(`/v1/domains/ai-decidable?${params.toString()}`)
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
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (letter) params.set('letter', letter)
  if (label) params.set('label', label)
  if (search?.trim()) params.set('search', search.trim())
  if (sortBy) params.set('sort_by', sortBy)
  if (sortDir) params.set('sort_dir', sortDir)
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
  const params = new URLSearchParams({ campaign_id: campaignId })
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  return request<AiReviewLabelCounts>(`/v1/ai-review/label-counts?${params.toString()}`)
}

export async function createAiReviewJob(body: AiReviewJobCreate): Promise<AiReviewJobRead> {
  return request<AiReviewJobRead>('/v1/ai-review/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
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
  const params = new URLSearchParams({ campaign_id: campaignId })
  if (scrapeStatus) params.set('scrape_status', scrapeStatus)
  return request<DomainLetterCounts>(`/v1/domains/letter-counts?${params.toString()}`)
}

export async function getDomainScrapeCounts(campaignId: string): Promise<DomainScrapeCounts> {
  return request<DomainScrapeCounts>(`/v1/domains/scrape-counts?campaign_id=${encodeURIComponent(campaignId)}`)
}

// ── S3 Email Fetch ───────────────────────────────────────────────────────────

export async function getEmailFetchCriteria(campaignId: string): Promise<EmailFetchCriteriaRead> {
  return request<EmailFetchCriteriaRead>(`/v1/email-fetch/criteria?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function saveEmailFetchCriteria(payload: EmailFetchCriteriaSaveRequest): Promise<EmailFetchCriteriaRead> {
  return request<EmailFetchCriteriaRead>('/v1/email-fetch/criteria', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function listEmailFetchCompanies(
  campaignId: string,
  {
    status,
    letter,
    search,
    sortBy,
    sortDir,
    limit = 200,
    offset = 0,
  }: {
    status?: 'all' | EmailFetchCompanyStatus
    letter?: string
    search?: string
    sortBy?: string
    sortDir?: 'asc' | 'desc'
    limit?: number
    offset?: number
  } = {},
): Promise<EmailFetchCompanyList> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  if (sortBy) params.set('sort_by', sortBy)
  if (sortDir) params.set('sort_dir', sortDir)
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
  const params = new URLSearchParams({ campaign_id: campaignId })
  if (status) params.set('status', status)
  if (search?.trim()) params.set('search', search.trim())
  return request<DomainLetterCounts>(`/v1/email-fetch/letter-counts?${params.toString()}`)
}

export async function listEmailFetchCompanyIds(
  campaignId: string,
  {
    status,
    letter,
    search,
    fetchableOnly = false,
    limit = 200,
    offset = 0,
  }: {
    status?: 'all' | EmailFetchCompanyStatus
    letter?: string
    search?: string
    fetchableOnly?: boolean
    limit?: number
    offset?: number
  } = {},
): Promise<EmailFetchCompanyIds> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  if (fetchableOnly) params.set('fetchable_only', 'true')
  return request<EmailFetchCompanyIds>(`/v1/email-fetch/company-ids?${params.toString()}`)
}

export async function previewEmailFetch(body: EmailFetchPreviewRequest): Promise<EmailFetchPreviewRead> {
  return request<EmailFetchPreviewRead>('/v1/email-fetch/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function createEmailFetchBatch(body: EmailFetchBatchCreate): Promise<EmailFetchBatchRead> {
  return request<EmailFetchBatchRead>('/v1/email-fetch/batches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function getEmailFetchBatch(batchId: string): Promise<EmailFetchBatchRead> {
  return request<EmailFetchBatchRead>(`/v1/email-fetch/batches/${encodeURIComponent(batchId)}`)
}

export async function getActiveEmailFetchBatch(campaignId: string): Promise<EmailFetchBatchRead | null> {
  return request<EmailFetchBatchRead | null>(`/v1/email-fetch/batches/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

// ── S4 Email Verification ───────────────────────────────────────────────────

export async function listEmailVerificationContacts(
  campaignId: string,
  {
    status,
    letter,
    search,
    sortBy,
    sortDir,
    limit = 50,
    offset = 0,
  }: {
    status?: 'all' | EmailVerificationStatus
    letter?: string
    search?: string
    sortBy?: string
    sortDir?: 'asc' | 'desc'
    limit?: number
    offset?: number
  } = {},
): Promise<EmailVerificationContactList> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  if (sortBy) params.set('sort_by', sortBy)
  if (sortDir) params.set('sort_dir', sortDir)
  return request<EmailVerificationContactList>(`/v1/email-verification/contacts?${params.toString()}`)
}

export async function listEmailVerificationContactIds(
  campaignId: string,
  {
    status,
    letter,
    search,
    actionableOnly = false,
    limit = 200,
    offset = 0,
  }: {
    status?: 'all' | EmailVerificationStatus
    letter?: string
    search?: string
    actionableOnly?: boolean
    limit?: number
    offset?: number
  } = {},
): Promise<EmailVerificationContactIds> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
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
  const params = new URLSearchParams({ campaign_id: campaignId })
  if (status) params.set('status', status)
  if (search?.trim()) params.set('search', search.trim())
  return request<DomainLetterCounts>(`/v1/email-verification/letter-counts?${params.toString()}`)
}

export async function previewEmailVerification(body: EmailVerificationPreviewRequest): Promise<EmailVerificationPreviewRead> {
  return request<EmailVerificationPreviewRead>('/v1/email-verification/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function createEmailVerificationBatch(body: EmailVerificationBatchCreate): Promise<EmailVerificationBatchRead> {
  return request<EmailVerificationBatchRead>('/v1/email-verification/batches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function getEmailVerificationBatch(batchId: string): Promise<EmailVerificationBatchRead> {
  return request<EmailVerificationBatchRead>(`/v1/email-verification/batches/${encodeURIComponent(batchId)}`)
}

export async function getActiveEmailVerificationBatch(campaignId: string): Promise<EmailVerificationBatchRead | null> {
  return request<EmailVerificationBatchRead | null>(`/v1/email-verification/batches/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function downloadFreshValidEmailCsv(campaignId: string): Promise<void> {
  const params = new URLSearchParams({ campaign_id: campaignId })
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
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
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
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (domainId) params.set('domain_id', domainId)
  if (status) params.set('status', status)
  return request<FetchedPersonList>(`/v1/fetched-people?${params.toString()}`)
}

// ── S1 Scrape Batches ─────────────────────────────────────────────────────────

export async function createScrapeBatch(body: ScrapeBatchCreate): Promise<ScrapeBatchRead> {
  return request<ScrapeBatchRead>('/v1/scrape-batches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function createScrapeJob(body: ScrapeBatchCreate): Promise<ScrapeBatchRead> {
  return request<ScrapeBatchRead>('/v1/scrape-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function listScrapeBatches(campaignId: string, limit = 20): Promise<ScrapeBatchList> {
  return request<ScrapeBatchList>(`/v1/scrape-batches?campaign_id=${encodeURIComponent(campaignId)}&limit=${limit}`)
}

export async function getActiveBatch(campaignId: string): Promise<ScrapeBatchRead | null> {
  return request<ScrapeBatchRead | null>(`/v1/scrape-batches/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function getScrapeBatch(batchId: string): Promise<ScrapeBatchRead> {
  return request<ScrapeBatchRead>(`/v1/scrape-batches/${batchId}`)
}

export async function getScrapeJobStatus(batchId: string): Promise<ScrapeJobStatusRead> {
  return request<ScrapeJobStatusRead>(`/v1/scrape-jobs/${encodeURIComponent(batchId)}/status`)
}

// ── S1 Scrape Settings ────────────────────────────────────────────────────────

export async function getScrapeSettings(campaignId: string): Promise<ScrapeSettingsRead | null> {
  return request<ScrapeSettingsRead | null>(`/v1/scrape-settings?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function listScrapeSettings(campaignId: string, limit = 20): Promise<ScrapeSettingsList> {
  return request<ScrapeSettingsList>(`/v1/scrape-settings/history?campaign_id=${encodeURIComponent(campaignId)}&limit=${limit}`)
}

export async function saveScrapeSettings(campaignId: string, instructionText: string): Promise<ScrapeSettingsRead> {
  return request<ScrapeSettingsRead>('/v1/scrape-settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ campaign_id: campaignId, instruction_text: instructionText }),
  })
}

export async function updateScrapeSettings(settingsId: string, payload: ScrapeSettingsUpdate): Promise<ScrapeSettingsRead> {
  return request<ScrapeSettingsRead>(`/v1/scrape-settings/${encodeURIComponent(settingsId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteScrapeSettings(settingsId: string): Promise<void> {
  await request<void>(`/v1/scrape-settings/${encodeURIComponent(settingsId)}`, { method: 'DELETE' })
}

// ── S2 Decision Settings ──────────────────────────────────────────────────────

export async function listDecisionSettings(
  campaignId: string,
  { limit = 50, offset = 0, isActive }: { limit?: number; offset?: number; isActive?: boolean } = {},
): Promise<DecisionSettingsList> {
  const params = new URLSearchParams({
    campaign_id: campaignId,
    limit: String(limit),
    offset: String(offset),
  })
  if (typeof isActive === 'boolean') params.set('is_active', String(isActive))
  return request<DecisionSettingsList>(`/v1/decision-settings?${params.toString()}`)
}

export async function getActiveDecisionSettings(campaignId: string): Promise<DecisionSettingsRead | null> {
  return request<DecisionSettingsRead | null>(`/v1/decision-settings/active?campaign_id=${encodeURIComponent(campaignId)}`)
}

export async function createDecisionSettings(payload: DecisionSettingsCreate): Promise<DecisionSettingsRead> {
  return request<DecisionSettingsRead>('/v1/decision-settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateDecisionSettings(settingsId: string, payload: DecisionSettingsUpdate): Promise<DecisionSettingsRead> {
  return request<DecisionSettingsRead>(`/v1/decision-settings/${encodeURIComponent(settingsId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function deleteDecisionSettings(settingsId: string): Promise<void> {
  await request<void>(`/v1/decision-settings/${encodeURIComponent(settingsId)}`, { method: 'DELETE' })
}

// ── S1 Scrape Results (content drawer) ───────────────────────────────────────

export async function getScrapeResult(domainId: string, campaignId: string): Promise<ScrapeResultRead | null> {
  const params = new URLSearchParams({ campaign_id: campaignId, domain_id: domainId })
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
  return request<IntegrationProviderStatus>(`/v1/settings/integrations/${encodeURIComponent(provider)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function testIntegrationProvider(provider: IntegrationProviderId): Promise<IntegrationTestResponse> {
  return request<IntegrationTestResponse>(`/v1/settings/integrations/${encodeURIComponent(provider)}/test`, { method: 'POST' })
}

export async function getIntegrationsHealth(): Promise<IntegrationHealthItem[]> {
  return request<IntegrationHealthItem[]>('/v1/settings/integrations/health')
}

// ── Utility ───────────────────────────────────────────────────────────────────

/**
 * Parse a date string as UTC.
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
