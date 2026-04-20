import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  assignUploadsToCampaign,
  configureApiSession,
  createCampaign,
  createRuns,
  createScrapeJob,
  deleteCampaign,
  fetchContactsSelected,
  drainQueue,
  fetchContactsForCompany,
  fetchContactsForCompanyApollo,
  getCurrentUser,
  getContactsExportUrl,
  getCampaignCosts,
  getCostStats,
  getCompanyCounts,
  getContactCounts,
  getPipelineRunProgress,
  getStats,
  loginWithPassword,
  listRuns,
  listCampaigns,
  listUploads,
  logoutSession,
  resetStuckJobs,
  startPipelineRun,
  uploadFileToCampaign,
} from './lib/api'
import type {
  CampaignRead,
  CompanyCounts,
  CompanyListItem,
  ContactCountsResponse,
  UploadRead,
  RunRead,
  ScrapeJobRead,
  StatsResponse,
  PipelineRunProgressRead,
  PipelineCostSummaryRead,
  CostStatsResponse,
} from './lib/types'
import { buildRouteSearch, parseRouteState, type ActiveView } from './lib/navigation'
import type { AuthSession } from './lib/auth'
import { parseApiError } from './lib/utils'

// Hooks
import { usePanels } from './hooks/usePanels'
import { usePromptManagement } from './hooks/usePromptManagement'
import { useScrapePromptManagement } from './hooks/useScrapePromptManagement'
import { usePipelineViews } from './hooks/usePipelineViews'

// Layout
import { AppShell } from './components/layout/AppShell'

// Pipeline views
import { DashboardView } from './components/views/pipeline/DashboardView'
import { FullPipelineView } from './components/views/pipeline/FullPipelineView'
import { S1ScrapingView } from './components/views/pipeline/S1ScrapingView'
import { S2AIDecisionView } from './components/views/pipeline/S2AIDecisionView'
import { S3ContactFetchView } from './components/views/pipeline/S3ContactFetchView'
import { S4ValidationView } from './components/views/pipeline/S4ValidationView'
import { CampaignsView } from './components/views/campaigns/CampaignsView'
import { OperationsLogView } from './components/views/OperationsLogView'
import { LoginView } from './components/views/auth/LoginView'
import { SettingsView } from './components/views/settings/SettingsView'
import { buildOperationsEvents } from './lib/telemetry'

// Panels
import { MarkdownPreviewPanel } from './components/panels/MarkdownPreviewPanel'
import { PromptLibraryPanel } from './components/panels/PromptLibraryPanel'
import { ScrapePromptLibraryPanel } from './components/panels/ScrapePromptLibraryPanel'
import { TitleRulesPanel } from './components/panels/TitleRulesPanel'
import { AnalysisDetailPanel } from './components/panels/AnalysisDetailPanel'
import { CompanyReviewPanel } from './components/panels/CompanyReviewPanel'
import { CompanyContactsPreviewPanel } from './components/panels/CompanyContactsPreviewPanel'
import { ScrapeDiagnosticsPanel } from './components/panels/ScrapeDiagnosticsPanel'

// UI
import { Toast, type ToastNoticeAction } from './components/ui/Toast'

const MAX_POLL_FAILURES = 3
const INITIAL_ROUTE_STATE = typeof window === 'undefined'
  ? { view: 'dashboard' as ActiveView, campaignId: null as string | null }
  : parseRouteState(window.location.search)
const AUTH_REQUIRED = ((import.meta as { env?: Record<string, string | undefined> }).env?.VITE_AUTH_REQUIRED ?? 'false') === 'true'

function App() {
  const pollFailuresRef = useRef(0)
  const campaignCostsRouteMissingRef = useRef(false)
  const selectedCampaignIdRef = useRef<string | null>(null)

  // ── Navigation ────────────────────────────────────────────────────────────
  const [activeView, setActiveView] = useState<ActiveView>(INITIAL_ROUTE_STATE.view)

  // ── Auth/session foundation ───────────────────────────────────────────────
  const [authSession, setAuthSession] = useState<AuthSession | null>(null)
  const [isAuthBootstrapping, setIsAuthBootstrapping] = useState(AUTH_REQUIRED)
  const [isSigningIn, setIsSigningIn] = useState(false)
  const [authError, setAuthError] = useState('')

  // ── Toasts ────────────────────────────────────────────────────────────────
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [noticeAction, setNoticeAction] = useState<ToastNoticeAction | null>(null)

  // ── Upload ────────────────────────────────────────────────────────────────
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragActive, setIsDragActive] = useState(false)

  // ── Stats + Counts ────────────────────────────────────────────────────────
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [companyCounts, setCompanyCounts] = useState<CompanyCounts | null>(null)
  const [contactCounts, setContactCounts] = useState<ContactCountsResponse | null>(null)

  // ── Recent data (for Dashboard) ───────────────────────────────────────────
  const [recentScrapeJobs, setRecentScrapeJobs] = useState<ScrapeJobRead[]>([])
  const [recentRuns, setRecentRuns] = useState<RunRead[]>([])
  const [campaigns, setCampaigns] = useState<CampaignRead[]>([])
  const [uploads, setUploads] = useState<UploadRead[]>([])
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(INITIAL_ROUTE_STATE.campaignId)
  const [isCampaignLoading, setIsCampaignLoading] = useState(false)
  const [isCampaignSaving, setIsCampaignSaving] = useState(false)
  const [latestPipelineRunId, setLatestPipelineRunId] = useState<string | null>(null)
  const [latestPipelineRunProgress, setLatestPipelineRunProgress] = useState<PipelineRunProgressRead | null>(null)
  const [campaignCostSummary, setCampaignCostSummary] = useState<PipelineCostSummaryRead | null>(null)
  const [campaignCostBreakdown, setCampaignCostBreakdown] = useState<CostStatsResponse | null>(null)
  const [operationsPipelineFilter, setOperationsPipelineFilter] = useState<'all' | 'scrape' | 'analysis'>('all')
  const [operationsStatusFilter, setOperationsStatusFilter] = useState<'all' | 'active' | 'completed' | 'failed'>('all')
  const [operationsErrorOnly, setOperationsErrorOnly] = useState(false)
  const [operationsSearchQuery, setOperationsSearchQuery] = useState('')
  const activeCampaignName =
    campaigns.find((c) => c.id === selectedCampaignId)?.name ??
    campaigns[0]?.name ??
    null
  const operationsEvents = useMemo(() => {
    const base = buildOperationsEvents(recentScrapeJobs, recentRuns)
    return base.filter((event) => {
      if (operationsPipelineFilter !== 'all' && event.kind !== operationsPipelineFilter) return false
      if (operationsStatusFilter !== 'all' && event.status !== operationsStatusFilter) return false
      if (operationsErrorOnly && !event.error_code) return false
      const query = operationsSearchQuery.trim().toLowerCase()
      if (!query) return true
      return event.search_blob.includes(query)
    })
  }, [operationsErrorOnly, operationsPipelineFilter, operationsSearchQuery, operationsStatusFilter, recentRuns, recentScrapeJobs])
  const operationsActiveCount = useMemo(
    () => operationsEvents.filter((event) => event.status === 'active').length,
    [operationsEvents],
  )
  const showScrapeFilter = recentScrapeJobs.length > 0
  const scrapeTelemetryNote = showScrapeFilter
    ? ''
    : 'Scrape timeline entries are temporarily hidden until campaign-scoped scrape telemetry is available.'

  // ── Per-row action state ──────────────────────────────────────────────────
  const [actionState, setActionState] = useState<Record<string, string>>({})
  const [analysisActionState, setAnalysisActionState] = useState<Record<string, string>>({})

  // ── Pipeline ops ──────────────────────────────────────────────────────────
  const [isDrainingQueue, setIsDrainingQueue] = useState(false)
  const [isResettingStuck, setIsResettingStuck] = useState(false)

  // ── Title rules panel ─────────────────────────────────────────────────────
  const [isTitleRulesOpen, setIsTitleRulesOpen] = useState(false)
  const [isStartingCampaignPipeline, setIsStartingCampaignPipeline] = useState(false)

  // ── Custom hooks ──────────────────────────────────────────────────────────
  const promptMgmt = usePromptManagement(setError, setNotice)
  const scrapePromptMgmt = useScrapePromptManagement(setError, setNotice)

  const pipeline = usePipelineViews(
    activeView,
    selectedCampaignId,
    promptMgmt.selectedPrompt,
    scrapePromptMgmt.activeScrapePrompt,
    setError,
    setNotice,
  )
  const refreshPipelineView = pipeline.refreshPipelineView

  const panels = usePanels(setError, setNotice, selectedCampaignId, refreshPipelineView)

  // ── Load functions ────────────────────────────────────────────────────────

  const loadStats = useCallback(async () => {
    if (!selectedCampaignId) {
      setStats(null)
      return
    }
    if (pollFailuresRef.current >= MAX_POLL_FAILURES) return
    const campaignId = selectedCampaignId
    try {
      const data = await getStats(campaignId)
      if (selectedCampaignIdRef.current !== campaignId) return
      setStats(data)
      pollFailuresRef.current = 0
    } catch {
      if (selectedCampaignIdRef.current !== campaignId) return
      pollFailuresRef.current += 1
    }
  }, [selectedCampaignId])

  const loadCompanyCounts = useCallback(async () => {
    if (!selectedCampaignId) {
      setCompanyCounts(null)
      return
    }
    try {
      const data = await getCompanyCounts(selectedCampaignId)
      setCompanyCounts(data)
    } catch { /* non-critical */ }
  }, [selectedCampaignId])

  const loadContactCounts = useCallback(async () => {
    if (!selectedCampaignId) {
      setContactCounts(null)
      return
    }
    try {
      const data = await getContactCounts(selectedCampaignId)
      setContactCounts(data)
    } catch { /* non-critical */ }
  }, [selectedCampaignId])

  const loadRecentActivity = useCallback(async () => {
    if (!selectedCampaignId) {
      setRecentScrapeJobs([])
      setRecentRuns([])
      return
    }
    const scopedUploadIds = new Set(
      uploads.filter((upload) => upload.campaign_id === selectedCampaignId).map((upload) => upload.id),
    )
    if (scopedUploadIds.size === 0) {
      setRecentScrapeJobs([])
      setRecentRuns([])
      return
    }
    try {
      const runRows = await listRuns(200, 0)
      // ScrapeJob rows lack campaign identifiers, so keep operations strictly scoped
      // by suppressing scrape timeline rows until a campaign-scoped scrape endpoint exists.
      setRecentScrapeJobs([])
      setRecentRuns(runRows.filter((run) => scopedUploadIds.has(run.upload_id)).slice(0, 50))
    } catch { /* non-critical */ }
  }, [selectedCampaignId, uploads])

  const loadCampaignData = useCallback(async () => {
    setIsCampaignLoading(true)
    try {
      const [campaignRows, uploadRows] = await Promise.all([
        listCampaigns(200, 0),
        listUploads(200, 0),
      ])
      setCampaigns(campaignRows.items)
      setUploads(uploadRows.items)
      if (campaignRows.items.length > 0) {
        if (selectedCampaignId && campaignRows.items.some((c) => c.id === selectedCampaignId)) {
          // keep current selection
        } else {
          const pilot = campaignRows.items.find((c) => c.name.toLowerCase().includes('pilot'))
          setSelectedCampaignId((pilot ?? campaignRows.items[0]).id)
        }
      } else if (selectedCampaignId) {
        setSelectedCampaignId(null)
      }
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsCampaignLoading(false)
    }
  }, [selectedCampaignId])

  const loadCampaignCostSummary = useCallback(async (campaignId: string | null) => {
    if (!campaignId) {
      setCampaignCostSummary(null)
      return
    }
    if (campaignCostsRouteMissingRef.current) {
      setCampaignCostSummary(null)
      return
    }
    try {
      const summary = await getCampaignCosts(campaignId)
      setCampaignCostSummary(summary)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        campaignCostsRouteMissingRef.current = true
      }
      setCampaignCostSummary(null)
      // non-critical telemetry path
    }
  }, [])

  const loadCampaignCostBreakdown = useCallback(async (campaignId: string | null) => {
    if (!campaignId) {
      setCampaignCostBreakdown(null)
      return
    }
    try {
      const rows = await getCostStats({ campaignId, windowDays: 365, limit: 200, offset: 0 })
      setCampaignCostBreakdown(rows)
    } catch {
      setCampaignCostBreakdown(null)
    }
  }, [])

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    configureApiSession({
      getAccessToken: () => authSession?.accessToken ?? null,
      onUnauthorized: () => {
        if (!AUTH_REQUIRED) return
        setAuthSession(null)
        setAuthError('Your session expired. Please sign in again.')
      },
    })
  }, [authSession])

  useEffect(() => {
    if (!AUTH_REQUIRED) {
      setIsAuthBootstrapping(false)
      return
    }
    let cancelled = false
    const bootstrap = async () => {
      try {
        const me = await getCurrentUser()
        if (cancelled) return
        setAuthSession({
          userEmail: me.email,
          displayName: me.display_name?.trim() || me.email,
          accessToken: null,
        })
      } catch {
        if (!cancelled) setAuthSession(null)
      } finally {
        if (!cancelled) setIsAuthBootstrapping(false)
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    void promptMgmt.loadPrompts()
    void scrapePromptMgmt.loadScrapePrompts()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    selectedCampaignIdRef.current = selectedCampaignId
  }, [selectedCampaignId])

  useEffect(() => {
    void loadCampaignData()
  }, [loadCampaignData])

  useEffect(() => {
    void loadStats()
    void loadCompanyCounts()
    void loadContactCounts()
    void loadRecentActivity()
    const timer = window.setInterval(() => {
      void loadStats()
      void loadCompanyCounts()
      void loadContactCounts()
      void loadCampaignCostSummary(selectedCampaignId)
      void loadCampaignCostBreakdown(selectedCampaignId)
    }, 10000)
    return () => window.clearInterval(timer)
  }, [loadStats, loadCompanyCounts, loadContactCounts, loadRecentActivity, loadCampaignCostSummary, loadCampaignCostBreakdown, selectedCampaignId])

  useEffect(() => {
    if (!selectedCampaignId) return
    const livePipelineViews: ActiveView[] = [
      'full-pipeline',
      's1-scraping',
      's2-ai',
      's3-contacts',
      's4-validation',
    ]
    if (!livePipelineViews.includes(activeView)) return
    const timer = window.setInterval(() => {
      refreshPipelineView({ background: true })
    }, 5000)
    return () => window.clearInterval(timer)
  }, [activeView, refreshPipelineView, selectedCampaignId])

  useEffect(() => {
    setCampaignCostSummary(null)
    setCampaignCostBreakdown(null)
    void loadCampaignCostSummary(selectedCampaignId)
    void loadCampaignCostBreakdown(selectedCampaignId)
    setLatestPipelineRunId(null)
    setLatestPipelineRunProgress(null)
  }, [loadCampaignCostBreakdown, loadCampaignCostSummary, selectedCampaignId])

  useEffect(() => {
    if (!latestPipelineRunId) return
    let cancelled = false
    const loadProgress = async () => {
      try {
        const progress = await getPipelineRunProgress(latestPipelineRunId)
        if (!cancelled) setLatestPipelineRunProgress(progress)
        if (!cancelled) {
          void loadCampaignCostSummary(progress.campaign_id)
          void loadCampaignCostBreakdown(progress.campaign_id)
        }
      } catch {
        // non-critical telemetry path
      }
    }
    void loadProgress()
    const timer = window.setInterval(() => {
      void loadProgress()
    }, 5000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [latestPipelineRunId, loadCampaignCostSummary, loadCampaignCostBreakdown])

  useEffect(() => {
    if (!error) return
    setNotice('')
    setNoticeAction(null)
  }, [error])

  useEffect(() => {
    if (showScrapeFilter) return
    if (operationsPipelineFilter !== 'scrape') return
    setOperationsPipelineFilter('all')
  }, [operationsPipelineFilter, showScrapeFilter])

  useEffect(() => {
    if (!error) return
    const t = window.setTimeout(() => setError(''), 5000)
    return () => window.clearTimeout(t)
  }, [error])

  useEffect(() => {
    if (!notice) return
    const t = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(t)
  }, [notice])

  // ── Upload ────────────────────────────────────────────────────────────────

  const onUpload = async (event: FormEvent) => {
    event.preventDefault()
    if (!file) { setError('Choose a file first.'); return }
    setError(''); setNotice(''); setIsUploading(true)
    try {
      await uploadFileToCampaign(file, selectedCampaignId || undefined)
      setFile(null)
      void loadCompanyCounts()
      refreshPipelineView()
      void loadRecentActivity()
      void loadCampaignData()
      setNotice(
        selectedCampaignId
          ? 'Upload assigned to selected campaign and companies refreshed.'
          : 'Upload parsed and companies refreshed.',
      )
    } catch (err) { setError(parseApiError(err)) }
    finally { setIsUploading(false) }
  }

  const onCreateCampaign = async (name: string, description: string) => {
    setIsCampaignSaving(true)
    setError('')
    try {
      const created = await createCampaign({ name, description })
      setSelectedCampaignId(created.id)
      setNotice(`Campaign "${created.name}" created.`)
      await loadCampaignData()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsCampaignSaving(false)
    }
  }

  const onDeleteCampaign = async (campaignId: string) => {
    setIsCampaignSaving(true)
    setError('')
    try {
      await deleteCampaign(campaignId)
      if (selectedCampaignId === campaignId) setSelectedCampaignId(null)
      setNotice('Campaign deleted.')
      await loadCampaignData()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsCampaignSaving(false)
    }
  }

  const onAssignUploads = async (campaignId: string, uploadIds: string[]) => {
    setIsCampaignSaving(true)
    setError('')
    try {
      const updated = await assignUploadsToCampaign(campaignId, uploadIds)
      setNotice(`Assigned ${uploadIds.length} upload(s) to "${updated.name}".`)
      await loadCampaignData()
      await loadCompanyCounts()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsCampaignSaving(false)
    }
  }

  // ── Per-row scrape (S1) ───────────────────────────────────────────────────

  const onScrape = async (company: CompanyListItem) => {
    if (company.latest_scrape_terminal === false) {
      setNotice(`Scrape already active for ${company.domain}.`); return
    }
    setError(''); setNotice('')
    setActionState((c) => ({ ...c, [company.id]: 'Creating…' }))
    try {
      await createScrapeJob({
        website_url: company.normalized_url,
        scrape_rules: scrapePromptMgmt.activeScrapePrompt?.scrape_rules_structured ?? undefined,
      })
      setActionState((c) => ({ ...c, [company.id]: 'Queued' }))
      refreshPipelineView()
      void loadRecentActivity()
    } catch (err) {
      setActionState((c) => ({ ...c, [company.id]: 'Failed' }))
      setError(parseApiError(err))
    }
  }

  // ── Per-row classify (S2) ─────────────────────────────────────────────────

  const onClassify = async (company: CompanyListItem) => {
    if (!promptMgmt.selectedPrompt?.enabled) {
      setError('Select an enabled prompt before running analysis.'); return
    }
    setAnalysisActionState((c) => ({ ...c, [company.id]: 'Queuing…' }))
    setError(''); setNotice('')
    try {
      const result = await createRuns({
        prompt_id: promptMgmt.selectedPrompt.id,
        scope: 'selected',
        company_ids: [company.id],
      })
      const skipped = new Set(result.skipped_company_ids)
      setAnalysisActionState((c) => ({ ...c, [company.id]: skipped.has(company.id) ? 'Skipped' : 'Queued' }))
      void loadRecentActivity()
    } catch (err) {
      setAnalysisActionState((c) => ({ ...c, [company.id]: 'Failed' }))
      setError(parseApiError(err))
    }
  }

  // ── Per-row contact fetch (S3) ────────────────────────────────────────────

  const onFetchContacts = async (company: CompanyListItem) => {
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    setError(''); setNotice('')
    try {
      const result = await fetchContactsForCompany(selectedCampaignId, company.id)
      const msg = result.queued_count > 0
        ? `Queued contact fetch for ${company.domain}.`
        : result.already_fetching_count > 0
          ? `Contact fetch already in progress for ${company.domain}.`
          : `No contacts queued for ${company.domain}.`
      setNotice(msg)
    } catch (err) { setError(parseApiError(err)) }
  }

  const onFetchContactsApollo = async (company: CompanyListItem) => {
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    setError(''); setNotice('')
    try {
      const result = await fetchContactsForCompanyApollo(selectedCampaignId, company.id)
      const msg = result.queued_count > 0
        ? `Queued Apollo fetch for ${company.domain}.`
        : result.already_fetching_count > 0
          ? `Apollo fetch already in progress for ${company.domain}.`
          : `No Apollo contacts queued for ${company.domain}.`
      setNotice(msg)
    } catch (err) { setError(parseApiError(err)) }
  }

  const onFetchContactsBoth = async (company: CompanyListItem) => {
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    setError(''); setNotice('')
    try {
      const result = await fetchContactsSelected(selectedCampaignId, [company.id], 'both')
      const msg = result.queued_count > 0
        ? `Queued sequential both-provider fetch for ${company.domain} (Snov first, Apollo follow-up).`
        : result.already_fetching_count > 0
          ? `Contact fetch already in progress for ${company.domain}; Apollo follow-up will be chained.`
          : `No contacts queued for ${company.domain}.`
      setNotice(msg)
    } catch (err) { setError(parseApiError(err)) }
  }

  // ── Pipeline ops ──────────────────────────────────────────────────────────

  const onDrainQueue = async () => {
    if (!window.confirm('Cancel all queued jobs? This removes them from Redis and marks them as cancelled.')) return
    setError(''); setNotice(''); setIsDrainingQueue(true)
    try {
      const result = await drainQueue()
      void loadStats()
      setNotice(`Cancelled ${result.cancelled_scrape_jobs.toLocaleString()} scrape jobs and ${result.cancelled_analysis_jobs.toLocaleString()} analysis jobs.`)
    } catch (err) { setError(parseApiError(err)) }
    finally { setIsDrainingQueue(false) }
  }

  const onResetStuck = async () => {
    setError(''); setNotice(''); setIsResettingStuck(true)
    try {
      const result = await resetStuckJobs()
      void loadStats()
      setNotice(`Reset and re-queued ${result.reset_count.toLocaleString()} stuck scrape jobs.`)
    } catch (err) { setError(parseApiError(err)) }
    finally { setIsResettingStuck(false) }
  }

  const onStartCampaignPipeline = async () => {
    if (!selectedCampaignId) {
      setError('Select a campaign before starting a pipeline run.')
      return
    }
    setError('')
    setNotice('')
    setNoticeAction(null)
    setIsStartingCampaignPipeline(true)
    try {
      const result = await startPipelineRun({
        campaign_id: selectedCampaignId,
        scrape_rules_snapshot: {
          scrape_prompt_id: scrapePromptMgmt.activeScrapePrompt?.id ?? null,
          scrape_prompt_name: scrapePromptMgmt.activeScrapePrompt?.name ?? null,
          intent_text: scrapePromptMgmt.activeScrapePrompt?.intent_text ?? null,
          compiled_prompt_text: scrapePromptMgmt.activeScrapePrompt?.compiled_prompt_text ?? null,
          scrape_rules_structured: scrapePromptMgmt.activeScrapePrompt?.scrape_rules_structured ?? null,
        },
        analysis_prompt_snapshot: promptMgmt.selectedPrompt
          ? {
              prompt_id: promptMgmt.selectedPrompt.id,
              prompt_name: promptMgmt.selectedPrompt.name,
              prompt_text: promptMgmt.selectedPrompt.prompt_text,
              enabled: promptMgmt.selectedPrompt.enabled,
            }
          : null,
      })
      setNotice(
        `Pipeline run ${result.pipeline_run_id} queued: requested ${result.requested_count}, reused ${result.reused_count}, queued ${result.queued_count}, skipped ${result.skipped_count}, failed ${result.failed_count}.`,
      )
      setLatestPipelineRunId(result.pipeline_run_id)
      void loadStats()
      void loadCompanyCounts()
      void loadRecentActivity()
      void loadCampaignData()
      void loadCampaignCostSummary(selectedCampaignId)
      refreshPipelineView()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsStartingCampaignPipeline(false)
    }
  }

  const syncUrlState = useCallback((state: { view: ActiveView; campaignId: string | null }, mode: 'push' | 'replace') => {
    if (typeof window === 'undefined') return
    const search = buildRouteSearch({ view: state.view, campaignId: state.campaignId })
    const nextUrl = `${window.location.pathname}${search}${window.location.hash}`
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
    if (nextUrl === currentUrl) return
    const method = mode === 'push' ? 'pushState' : 'replaceState'
    window.history[method]({}, '', nextUrl)
  }, [])

  const setCampaignFromUser = useCallback((campaignId: string | null) => {
    setSelectedCampaignId(campaignId)
    syncUrlState({ view: activeView, campaignId }, 'push')
  }, [activeView, syncUrlState])

  const requiresCampaignScope = activeView !== 'dashboard' && activeView !== 'campaigns' && activeView !== 'settings'

  const navigateToView = useCallback((view: ActiveView) => {
    const viewNeedsCampaign = view !== 'dashboard' && view !== 'campaigns' && view !== 'settings'
    if (viewNeedsCampaign && !selectedCampaignId) {
      setActiveView('campaigns')
      syncUrlState({ view: 'campaigns', campaignId: selectedCampaignId }, 'push')
      setNotice('Select a campaign first, then continue to the pipeline stage.')
      setNoticeAction({
        label: 'Open Campaigns',
        onClick: () => setActiveView('campaigns'),
      })
      return
    }
    setNoticeAction(null)
    setActiveView(view)
    syncUrlState({ view, campaignId: selectedCampaignId }, 'push')
  }, [selectedCampaignId, syncUrlState])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const onPopState = () => {
      const routeState = parseRouteState(window.location.search)
      setActiveView(routeState.view)
      setSelectedCampaignId(routeState.campaignId)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    syncUrlState({ view: activeView, campaignId: selectedCampaignId }, 'replace')
  }, [activeView, selectedCampaignId, syncUrlState])

  const handleLogin = useCallback(async (email: string, password: string) => {
    if (!email.trim() || !password.trim()) {
      setAuthError('Email and password are required.')
      return
    }
    setIsSigningIn(true)
    setAuthError('')
    try {
      const response = await loginWithPassword(email.trim(), password)
      setAuthSession({
        userEmail: response.user.email,
        displayName: response.user.display_name?.trim() || response.user.email,
        accessToken: response.access_token ?? null,
      })
    } catch (err) {
      setAuthError(parseApiError(err))
    } finally {
      setIsSigningIn(false)
    }
  }, [])

  const handleLogout = useCallback(async () => {
    try {
      await logoutSession()
    } catch {
      // Session might already be invalid; still clear local auth state.
    }
    setAuthSession(null)
    setAuthError('')
    setNotice('Signed out.')
    setNoticeAction(null)
  }, [])

  if (AUTH_REQUIRED && isAuthBootstrapping) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-(--oc-bg)">
        <p className="text-sm text-(--oc-muted)">Checking session…</p>
      </main>
    )
  }

  if (AUTH_REQUIRED && !authSession) {
    return (
      <LoginView
        isSubmitting={isSigningIn}
        error={authError}
        onLogin={handleLogin}
      />
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <AppShell className="min-h-0 flex-1"
        activeView={activeView}
        setActiveView={navigateToView}
        activeCampaignName={activeCampaignName}
        stats={stats}
        onOpenPromptLibrary={activeView === 's1-scraping' ? scrapePromptMgmt.openScrapePromptSheet : promptMgmt.openPromptSheet}
        authEnabled={AUTH_REQUIRED}
        userDisplayName={authSession?.displayName ?? null}
        onLogout={AUTH_REQUIRED ? handleLogout : undefined}
      >
        {requiresCampaignScope && !selectedCampaignId ? (
          <div className="space-y-3 rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-6">
            <p className="text-sm text-(--oc-muted)">
              Select a campaign from Campaigns to view scoped pipeline data.
            </p>
            <button
              type="button"
              className="rounded-xl bg-(--oc-accent) px-3 py-2 text-xs font-bold text-white"
              onClick={() => navigateToView('campaigns')}
            >
              Go to Campaigns
            </button>
          </div>
        ) : null}

        {activeView === 'dashboard' && (
          <DashboardView
            companyCounts={companyCounts}
            stats={stats}
            recentScrapeJobs={recentScrapeJobs}
            recentRuns={recentRuns}
            file={file}
            isUploading={isUploading}
            isDragActive={isDragActive}
            onSetFile={setFile}
            onSetIsDragActive={setIsDragActive}
            onUpload={onUpload}
            hasSelectedCampaign={Boolean(selectedCampaignId)}
            onNavigate={(view) => navigateToView(view)}
            onOpenCampaigns={() => navigateToView('campaigns')}
            onOpenOperations={() => navigateToView('operations')}
          />
        )}

        {selectedCampaignId && activeView === 'operations' && (
          <OperationsLogView
            activeCampaignName={activeCampaignName}
            campaignCostSummary={campaignCostSummary}
            campaignCostBreakdown={campaignCostBreakdown}
            events={operationsEvents}
            isLoading={false}
            error={selectedCampaignId ? '' : 'Select a campaign to view operations.'}
            pipelineFilter={operationsPipelineFilter}
            statusFilter={operationsStatusFilter}
            errorOnly={operationsErrorOnly}
            searchQuery={operationsSearchQuery}
            activeCount={operationsActiveCount}
            showScrapeFilter={showScrapeFilter}
            scrapeTelemetryNote={scrapeTelemetryNote}
            onSetPipelineFilter={setOperationsPipelineFilter}
            onSetStatusFilter={setOperationsStatusFilter}
            onSetErrorOnly={setOperationsErrorOnly}
            onSetSearchQuery={setOperationsSearchQuery}
            onRefresh={() => void loadRecentActivity()}
            onInspectEvent={(event) => {
              if (event.scrape_job) {
                void panels.openScrapeDiagnostics(event.scrape_job)
                return
              }
              if (event.run) {
                void panels.loadRunJobs(event.run)
              }
            }}
          />
        )}

        {activeView === 'campaigns' && (
          <CampaignsView
            campaigns={campaigns}
            uploads={uploads}
            selectedCampaignId={selectedCampaignId}
            isLoading={isCampaignLoading}
            isSaving={isCampaignSaving}
            onSelectCampaign={setCampaignFromUser}
            onCreateCampaign={(name, description) => void onCreateCampaign(name, description)}
            onDeleteCampaign={(campaignId) => void onDeleteCampaign(campaignId)}
            onAssignUploads={(campaignId, uploadIds) => void onAssignUploads(campaignId, uploadIds)}
            onStartCampaignPipeline={() => void onStartCampaignPipeline()}
            onOpenFullPipeline={() => navigateToView('full-pipeline')}
            isStartingCampaignPipeline={isStartingCampaignPipeline}
            latestRunProgress={latestPipelineRunProgress}
            campaignCostSummary={campaignCostSummary}
          />
        )}

        {activeView === 'settings' && (
          <SettingsView />
        )}

        {selectedCampaignId && activeView === 'full-pipeline' && (
          <FullPipelineView
            activeCampaignName={activeCampaignName}
            companies={pipeline.fullPipelineCompanies}
            letterCounts={pipeline.fullPipelineLetterCounts}
            activeLetter={pipeline.fullPipelineActiveLetter}
            selectedIds={pipeline.fullPipelineSelectedIds}
            resumeActionState={pipeline.fullPipelineResumeState}
            isLoading={pipeline.isFullPipelineLoading}
            offset={pipeline.fullPipelineOffset}
            pageSize={pipeline.fullPipelinePageSize}
            isScraping={pipeline.isFullPipelineScraping}
            isSelectingAllMatching={pipeline.isFullPipelineSelectingAllMatching}
            onSelectAllMatching={pipeline.onFullPipelineSelectAllMatching}
            onLetterChange={pipeline.onFullPipelineLetterChange}
            onToggleRow={pipeline.onFullPipelineToggleRow}
            onToggleAll={pipeline.onFullPipelineToggleAll}
            onClearSelection={pipeline.onFullPipelineClearSelection}
            onScrapeSelected={pipeline.onFullPipelineScrapeSelected}
            onStartCampaignPipeline={() => void onStartCampaignPipeline()}
            onResumeCompany={pipeline.onFullPipelineResumeCompany}
            onPagePrev={pipeline.onFullPipelinePagePrev}
            onPageNext={pipeline.onFullPipelinePageNext}
            onPageSizeChange={pipeline.onFullPipelinePageSizeChange}
            isStartingCampaignPipeline={isStartingCampaignPipeline}
            latestRunProgress={latestPipelineRunProgress}
            campaignCostSummary={campaignCostSummary}
            campaignCostBreakdown={campaignCostBreakdown}
          />
        )}

        {selectedCampaignId && activeView === 's1-scraping' && (
          <S1ScrapingView
            companies={pipeline.pipelineCompanies}
            letterCounts={pipeline.pipelineLetterCounts}
            activeLetters={pipeline.pipelineActiveLetters}
            scrapeSubFilter={pipeline.pipelineScrapeSubFilter}
            selectedScrapePrompt={scrapePromptMgmt.activeScrapePrompt}
            selectedIds={pipeline.pipelineSelectedIds}
            totalMatching={pipeline.pipelineCompanies?.total ?? null}
            isLoading={pipeline.isPipelineLoading}
            isScraping={pipeline.isPipelineScraping}
            isSelectingAll={pipeline.isPipelineSelectingAll}
            stats={stats}
            isResettingStuck={isResettingStuck}
            isDrainingQueue={isDrainingQueue}
            actionState={actionState}
            onScrapeSubFilterChange={pipeline.onPipelineScrapeSubFilterChange}
            onToggleLetter={pipeline.onPipelineToggleLetter}
            onClearLetters={pipeline.onPipelineClearLetters}
            onToggleRow={pipeline.onPipelineToggleRow}
            onToggleAll={pipeline.onPipelineToggleAll}
            onSelectAllMatching={pipeline.onPipelineSelectAllMatching}
            onClearSelection={pipeline.onPipelineClearSelection}
            onScrapeSelected={pipeline.onPipelineScrapeSelected}
            onScrapeOne={(c) => void onScrape(c)}
            onOpenPromptLibrary={scrapePromptMgmt.openScrapePromptSheet}
            onOpenDiagnostics={(c) => {
              if (c.latest_scrape_job_id) {
                void panels.openScrapeDiagnostics({ id: c.latest_scrape_job_id } as ScrapeJobRead)
              }
            }}
            onResetStuck={() => void onResetStuck()}
            onDrainQueue={() => void onDrainQueue()}
            offset={pipeline.pipelineOffset}
            pageSize={pipeline.pipelinePageSize}
            onPagePrev={pipeline.onPipelinePagePrev}
            onPageNext={pipeline.onPipelinePageNext}
            onPageSizeChange={pipeline.onPipelinePageSizeChange}
            sortBy={pipeline.pipelineSortBy}
            sortDir={pipeline.pipelineSortDir}
            onSort={pipeline.onPipelineSort}
          />
        )}

        {selectedCampaignId && activeView === 's2-ai' && (
          <S2AIDecisionView
            companies={pipeline.pipelineCompanies}
            letterCounts={pipeline.pipelineLetterCounts}
            activeLetters={pipeline.pipelineActiveLetters}
            decisionFilter={pipeline.pipelineDecisionFilter}
            selectedIds={pipeline.pipelineSelectedIds}
            totalMatching={pipeline.pipelineCompanies?.total ?? null}
            isLoading={pipeline.isPipelineLoading}
            isAnalyzing={pipeline.isPipelineAnalyzing}
            isSelectingAll={pipeline.isPipelineSelectingAll}
            prompts={promptMgmt.prompts}
            selectedPrompt={promptMgmt.selectedPrompt}
            recentRuns={recentRuns}
            analysisActionState={analysisActionState}
            manualLabelActionState={pipeline.pipelineManualLabelActionState}
            stats={stats}
            onDecisionFilterChange={pipeline.onPipelineDecisionFilterChange}
            onToggleLetter={pipeline.onPipelineToggleLetter}
            onClearLetters={pipeline.onPipelineClearLetters}
            onToggleRow={pipeline.onPipelineToggleRow}
            onToggleAll={pipeline.onPipelineToggleAll}
            onSelectAllMatching={pipeline.onPipelineSelectAllMatching}
            onClearSelection={pipeline.onPipelineClearSelection}
            onAnalyzeSelected={pipeline.onPipelineAnalyzeSelected}
            onClassifyOne={(c) => void onClassify(c)}
            onSetManualLabel={(c, label) => void pipeline.onPipelineSetManualLabel(c, label)}
            onReviewCompany={(c) => void panels.openCompanyReview(c)}
            onViewMarkdown={(c) => {
              if (c.latest_scrape_job_id) {
                void panels.openMarkdownDrawer({ id: c.latest_scrape_job_id } as ScrapeJobRead)
              }
            }}
            onOpenPromptLibrary={promptMgmt.openPromptSheet}
            offset={pipeline.pipelineOffset}
            pageSize={pipeline.pipelinePageSize}
            onPagePrev={pipeline.onPipelinePagePrev}
            onPageNext={pipeline.onPipelinePageNext}
            onPageSizeChange={pipeline.onPipelinePageSizeChange}
            sortBy={pipeline.pipelineSortBy}
            sortDir={pipeline.pipelineSortDir}
            onSort={pipeline.onPipelineSort}
          />
        )}

        {selectedCampaignId && activeView === 's3-contacts' && (
          <S3ContactFetchView
            campaignId={selectedCampaignId}
            companies={pipeline.pipelineCompanies}
            letterCounts={pipeline.pipelineLetterCounts}
            activeLetters={pipeline.pipelineActiveLetters}
            decisionFilter={pipeline.pipelineDecisionFilter}
            selectedIds={pipeline.pipelineSelectedIds}
            totalMatching={pipeline.pipelineCompanies?.total ?? null}
            isLoading={pipeline.isPipelineLoading}
            isFetching={pipeline.isPipelineFetching}
            isSelectingAll={pipeline.isPipelineSelectingAll}
            contactCounts={contactCounts}
            stats={stats}
            onDecisionFilterChange={pipeline.onPipelineDecisionFilterChange}
            onToggleLetter={pipeline.onPipelineToggleLetter}
            onClearLetters={pipeline.onPipelineClearLetters}
            onToggleRow={pipeline.onPipelineToggleRow}
            onToggleAll={pipeline.onPipelineToggleAll}
            onSelectAllMatching={pipeline.onPipelineSelectAllMatching}
            onClearSelection={pipeline.onPipelineClearSelection}
            onFetchOne={(c, source) => {
              if (source === 'snov') { void onFetchContacts(c) }
              else if (source === 'apollo') { void onFetchContactsApollo(c) }
              else { void onFetchContactsBoth(c) }
            }}
            onFetchSelected={pipeline.onPipelineFetchContacts}
            onViewContacts={(company) => void panels.openCompanyContacts(company)}
            onOpenTitleRules={() => setIsTitleRulesOpen(true)}
            offset={pipeline.pipelineOffset}
            pageSize={pipeline.pipelinePageSize}
            onPagePrev={pipeline.onPipelinePagePrev}
            onPageNext={pipeline.onPipelinePageNext}
            onPageSizeChange={pipeline.onPipelinePageSizeChange}
            sortBy={pipeline.pipelineSortBy}
            sortDir={pipeline.pipelineSortDir}
            onSort={pipeline.onPipelineSort}
          />
        )}

        {selectedCampaignId && activeView === 's4-validation' && (
          <S4ValidationView
            contacts={pipeline.s4Contacts}
            letterCounts={pipeline.s4LetterCounts}
            activeLetters={pipeline.s4ActiveLetters}
            verifFilter={pipeline.s4VerifFilter}
            selectedContactIds={pipeline.s4SelectedContactIds}
            totalMatching={pipeline.s4Contacts?.total ?? null}
            contactCounts={contactCounts}
            stats={stats}
            isLoading={pipeline.isS4Loading}
            isValidating={pipeline.isS4Validating}
            isSelectingAll={false}
            exportUrl={selectedCampaignId ? getContactsExportUrl({ campaignId: selectedCampaignId }) : ''}
            onVerifFilterChange={pipeline.onS4VerifFilterChange}
            onToggleLetter={pipeline.onS4ToggleLetter}
            onClearLetters={pipeline.onS4ClearLetters}
            offset={pipeline.s4Offset}
            pageSize={pipeline.s4PageSize}
            onPagePrev={pipeline.onS4PagePrev}
            onPageNext={pipeline.onS4PageNext}
            onPageSizeChange={pipeline.onS4PageSizeChange}
            onToggleContact={pipeline.onS4ToggleContact}
            onToggleAll={pipeline.onS4ToggleAll}
            onSelectAllMatching={() => { /* TODO: bulk select S4 contacts */ }}
            onClearSelection={pipeline.onS4ClearSelection}
            onValidateSelected={pipeline.onS4ValidateSelected}
            sortBy={pipeline.s4SortBy}
            sortDir={pipeline.s4SortDir}
            onSort={pipeline.onS4Sort}
          />
        )}
      </AppShell>

      {/* Panels */}
      <MarkdownPreviewPanel
        markdownJob={panels.markdownJob}
        markdownPages={panels.markdownPages}
        activeMarkdownPageKind={panels.activeMarkdownPageKind}
        isMarkdownLoading={panels.isMarkdownLoading}
        markdownError={panels.markdownError}
        markdownCopyState={panels.markdownCopyState}
        onClose={panels.closeMarkdownDrawer}
        onSetActivePageKind={panels.setActiveMarkdownPageKind}
        onCopyMarkdown={(content) => void panels.copyMarkdown(content)}
      />

      <ScrapeDiagnosticsPanel
        job={panels.diagnosticsJob}
        pages={panels.diagnosticsPages}
        isLoading={panels.isDiagnosticsLoading}
        error={panels.diagnosticsError}
        onClose={panels.closeScrapeDiagnostics}
        onOpenMarkdown={(job) => void panels.openMarkdownFromDiagnostics(job)}
      />

      <PromptLibraryPanel
        isOpen={promptMgmt.promptSheetOpen}
        onClose={promptMgmt.closePromptSheet}
        prompts={promptMgmt.prompts}
        selectedPromptId={promptMgmt.selectedPromptId}
        editingPromptId={promptMgmt.editingPromptId}
        promptName={promptMgmt.promptName}
        promptText={promptMgmt.promptText}
        promptEnabled={promptMgmt.promptEnabled}
        isPromptsLoading={promptMgmt.isPromptsLoading}
        isPromptSaving={promptMgmt.isPromptSaving}
        isPromptDeleting={promptMgmt.isPromptDeleting}
        promptError={promptMgmt.promptError}
        onSelectPrompt={promptMgmt.onSelectPrompt}
        onNewPrompt={promptMgmt.onNewPrompt}
        onTogglePromptEnabled={(p) => void promptMgmt.onTogglePromptEnabled(p)}
        onDeletePrompt={(p) => void promptMgmt.onDeletePrompt(p)}
        onClonePrompt={(p) => void promptMgmt.onClonePrompt(p)}
        onSaveAsNew={() => void promptMgmt.onSavePromptAsNew()}
        onUpdateCurrent={() => void promptMgmt.onUpdateCurrentPrompt()}
        onSetPromptName={promptMgmt.setPromptName}
        onSetPromptText={promptMgmt.setPromptText}
        onSetPromptEnabled={promptMgmt.setPromptEnabled}
        onRefresh={() => void promptMgmt.loadPrompts(promptMgmt.selectedPromptId, promptMgmt.editingPromptId !== null)}
      />

      <ScrapePromptLibraryPanel
        isOpen={scrapePromptMgmt.scrapePromptSheetOpen}
        onClose={scrapePromptMgmt.closeScrapePromptSheet}
        prompts={scrapePromptMgmt.scrapePrompts}
        selectedPromptId={scrapePromptMgmt.selectedScrapePromptId}
        activePromptId={scrapePromptMgmt.activeScrapePromptId}
        editingPromptId={scrapePromptMgmt.editingScrapePromptId}
        promptName={scrapePromptMgmt.scrapePromptName}
        promptIntentText={scrapePromptMgmt.scrapePromptIntentText}
        promptEnabled={scrapePromptMgmt.scrapePromptEnabled}
        isPromptsLoading={scrapePromptMgmt.isScrapePromptsLoading}
        isPromptSaving={scrapePromptMgmt.isScrapePromptSaving}
        isPromptDeleting={scrapePromptMgmt.isScrapePromptDeleting}
        promptError={scrapePromptMgmt.scrapePromptError}
        onSelectPrompt={scrapePromptMgmt.onSelectScrapePrompt}
        onNewPrompt={scrapePromptMgmt.onNewScrapePrompt}
        onTogglePromptEnabled={(p) => void scrapePromptMgmt.onToggleScrapePromptEnabled(p)}
        onDeletePrompt={(p) => void scrapePromptMgmt.onDeleteScrapePrompt(p)}
        onActivatePrompt={(p) => void scrapePromptMgmt.onActivateScrapePrompt(p)}
        onSaveAsNew={() => void scrapePromptMgmt.onSaveScrapePromptAsNew()}
        onUpdateCurrent={() => void scrapePromptMgmt.onUpdateCurrentScrapePrompt()}
        onSetPromptName={scrapePromptMgmt.setScrapePromptName}
        onSetPromptIntentText={scrapePromptMgmt.setScrapePromptIntentText}
        onSetPromptEnabled={scrapePromptMgmt.setScrapePromptEnabled}
        onRefresh={() =>
          void scrapePromptMgmt.loadScrapePrompts(
            scrapePromptMgmt.selectedScrapePromptId,
            scrapePromptMgmt.editingScrapePromptId !== null,
          )
        }
      />

      <AnalysisDetailPanel
        inspectedRun={panels.inspectedRun}
        runJobs={panels.runJobs}
        isRunJobsLoading={panels.isRunJobsLoading}
        runJobsError={panels.runJobsError}
        analysisDetail={panels.analysisDetail}
        isAnalysisDetailLoading={panels.isAnalysisDetailLoading}
        analysisDetailError={panels.analysisDetailError}
        onClose={panels.closeRunDrawer}
        onInspectJob={(job) => void panels.openAnalysisDetail(job)}
        onBackFromDetail={() => { panels.setAnalysisDetail(null); panels.setAnalysisDetailError('') }}
      />

      <CompanyReviewPanel
        company={panels.reviewedCompany}
        detail={panels.companyReviewDetail}
        isLoading={panels.isCompanyReviewLoading}
        error={panels.companyReviewError}
        isSaving={panels.isFeedbackSaving}
        onClose={panels.closeCompanyReview}
        onSave={(thumbs, comment) => void panels.saveFeedback(thumbs, comment)}
      />

      <CompanyContactsPreviewPanel
        campaignId={selectedCampaignId}
        company={panels.companyContactsCompany}
        contacts={panels.companyContacts}
        summary={panels.companyContactSummary}
        matchGapFilter={panels.companyContactGapFilter}
        isLoading={panels.isCompanyContactsLoading}
        error={panels.companyContactsError}
        onMatchGapFilterChange={panels.setCompanyContactGapFilter}
        onClose={panels.closeCompanyContacts}
      />

      <Toast error={error} notice={notice} noticeAction={noticeAction} />

      <TitleRulesPanel
        campaignId={selectedCampaignId}
        isOpen={isTitleRulesOpen}
        onClose={() => setIsTitleRulesOpen(false)}
      />
    </>
  )
}

export default App
