import type {
  CampaignCreate,
  CampaignList,
  CampaignRead,
  DomainList,
  DomainLetterCounts,
  DomainScrapeCounts,
  IntegrationHealthItem,
  IntegrationProviderId,
  IntegrationProviderStatus,
  IntegrationProviderUpdateRequest,
  IntegrationTestResponse,
  IntegrationsStatusResponse,
  PipelineCostSummaryRead,
  QueueHistoryResponse,
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
    limit = 50,
    offset = 0,
  }: {
    uploadId?: string
    scrapeStatus?: string
    letter?: string
    search?: string
    limit?: number
    offset?: number
  } = {},
): Promise<DomainList> {
  const params = new URLSearchParams({ campaign_id: campaignId, limit: String(limit), offset: String(offset) })
  if (uploadId) params.set('upload_id', uploadId)
  if (scrapeStatus) params.set('scrape_status', scrapeStatus)
  if (letter) params.set('letter', letter)
  if (search?.trim()) params.set('search', search.trim())
  return request<DomainList>(`/v1/companies?${params.toString()}`)
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

// ── Queue History ─────────────────────────────────────────────────────────────

export async function getQueueHistory(params: {
  campaignId?: string | null
  stage?: string
  view?: string
  limit?: number
  offset?: number
}): Promise<QueueHistoryResponse> {
  const q = new URLSearchParams()
  if (params.campaignId) q.set('campaign_id', params.campaignId)
  if (params.stage && params.stage !== 'all') q.set('stage', params.stage)
  if (params.view && params.view !== 'all') q.set('view', params.view)
  if (params.limit !== undefined) q.set('limit', String(params.limit))
  if (params.offset !== undefined) q.set('offset', String(params.offset))
  const qs = q.toString()
  return request<QueueHistoryResponse>(`/v1/queue-history${qs ? `?${qs}` : ''}`)
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
