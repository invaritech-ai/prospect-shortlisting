import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  configureApiSession,
  createCampaign,
  deleteCampaign,
  getCurrentUser,
  getCampaignCosts,
  getCostStats,
  getCompanyCounts,
  getContactCounts,
  getDiscoveredContactCounts,
  getIntegrationsHealth,
  getPipelineRunProgress,
  getStats,
  loginWithPassword,
  listRuns,
  listScrapeJobs,
  listCampaigns,
  listUploads,
  logoutSession,
  startPipelineRun,
  uploadFileToCampaign,
} from './lib/api'
import { ImportView } from './components/views/import/ImportView'
import type {
  CampaignRead,
  CompanyCounts,
  ContactCountsResponse,
  DiscoveredContactCountsResponse,
  IntegrationHealthItem,
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
import { ScrapingView } from './components/views/scraping/ScrapingView'
import { AIReviewView } from './components/views/ai-review/AIReviewView'
import { ContactsView } from './components/views/contacts/ContactsView'
import { S4RevealView } from './components/views/pipeline/S4RevealView'
import { ValidationView } from './components/views/validation/ValidationView'
import { CampaignsView } from './components/views/campaigns/CampaignsView'
import { OperationsLogView } from './components/views/OperationsLogView'
import { QueueHistoryView } from './components/views/QueueHistoryView'
import { LoginView } from './components/views/auth/LoginView'
import { SettingsView } from './components/views/settings/SettingsView'
import { MOCK_STATS, MOCK_COMPANY_COUNTS } from './lib/useAppData'
import { buildOperationsEvents } from './lib/telemetry'
import { useCampaignEventStream } from './lib/useCampaignEventStream'

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
import { GlobalLoadingOverlay } from './components/ui/GlobalLoadingOverlay'
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
  const authRequestsEnabled = !AUTH_REQUIRED || (!isAuthBootstrapping && authSession !== null)

  // ── Toasts ────────────────────────────────────────────────────────────────
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [noticeAction, setNoticeAction] = useState<ToastNoticeAction | null>(null)

  // ── Stats + Counts ────────────────────────────────────────────────────────
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [companyCounts, setCompanyCounts] = useState<CompanyCounts | null>(null)
  const [_contactCounts, setContactCounts] = useState<ContactCountsResponse | null>(null)
  const [_discoveredContactCounts, setDiscoveredContactCounts] = useState<DiscoveredContactCountsResponse | null>(null)

  // ── Recent data (for Dashboard) ───────────────────────────────────────────
  const [recentScrapeJobs, setRecentScrapeJobs] = useState<ScrapeJobRead[]>([])
  const [recentRuns, setRecentRuns] = useState<RunRead[]>([])
  const [campaigns, setCampaigns] = useState<CampaignRead[]>([])
  const [uploads, setUploads] = useState<UploadRead[]>([])
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(INITIAL_ROUTE_STATE.campaignId)
  const [_isCampaignLoading, setIsCampaignLoading] = useState(false)
  const [_isCampaignSaving, setIsCampaignSaving] = useState(false)
  const [busyMessage, setBusyMessage] = useState<string | null>(null)
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

  // ── Services health ───────────────────────────────────────────────────────
  const [servicesHealth, setServicesHealth] = useState<IntegrationHealthItem[] | null>(null)
  const [isLoadingHealth, setIsLoadingHealth] = useState(false)

  // ── Title rules panel ─────────────────────────────────────────────────────
  const [isTitleRulesOpen, setIsTitleRulesOpen] = useState(false)
  const [titleRulesNewCountAtOpen, setTitleRulesNewCountAtOpen] = useState(0)
  const [isStartingCampaignPipeline, setIsStartingCampaignPipeline] = useState(false)

  // ── Custom hooks ──────────────────────────────────────────────────────────
  const promptMgmt = usePromptManagement(setError, setNotice)
  const scrapePromptMgmt = useScrapePromptManagement(setError, setNotice)

  const pipeline = usePipelineViews(
    activeView,
    selectedCampaignId,
    promptMgmt.selectedPrompt,
    scrapePromptMgmt.activeScrapePrompt,
    authRequestsEnabled,
    setError,
    setNotice,
    stats,
  )
  const refreshPipelineView = pipeline.refreshPipelineView
  const cancelStaleSelectAllRequests = pipeline.cancelStaleSelectAllRequests
  const setSelectedCampaignIdAndCancel = useCallback((campaignId: string | null) => {
    cancelStaleSelectAllRequests()
    setSelectedCampaignId(campaignId)
  }, [cancelStaleSelectAllRequests])
  const setActiveViewAndCancel = useCallback((view: ActiveView) => {
    cancelStaleSelectAllRequests()
    setActiveView(view)
  }, [cancelStaleSelectAllRequests])

  const panels = usePanels(setError, setNotice, selectedCampaignId, refreshPipelineView)

  // ── Load functions ────────────────────────────────────────────────────────

  const loadServicesHealth = useCallback(async () => {
    if (!authRequestsEnabled) return
    setIsLoadingHealth(true)
    try {
      setServicesHealth(await getIntegrationsHealth())
    } catch { /* non-critical */ }
    finally { setIsLoadingHealth(false) }
  }, [authRequestsEnabled])

  const loadStats = useCallback(async () => {
    if (!authRequestsEnabled) {
      setStats(null)
      return
    }
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
      if (pollFailuresRef.current === 1) setStats(MOCK_STATS)
    }
  }, [authRequestsEnabled, selectedCampaignId])

  const loadCompanyCounts = useCallback(async () => {
    if (!authRequestsEnabled) {
      setCompanyCounts(null)
      return
    }
    if (!selectedCampaignId) {
      setCompanyCounts(null)
      return
    }
    try {
      const data = await getCompanyCounts(selectedCampaignId)
      setCompanyCounts(data)
    } catch { setCompanyCounts(MOCK_COMPANY_COUNTS) }
  }, [authRequestsEnabled, selectedCampaignId])

  const loadContactCounts = useCallback(async () => {
    if (!authRequestsEnabled) {
      setContactCounts(null)
      return
    }
    if (!selectedCampaignId) {
      setContactCounts(null)
      return
    }
    try {
      const data = await getContactCounts(selectedCampaignId)
      setContactCounts(data)
    } catch { /* non-critical */ }
  }, [authRequestsEnabled, selectedCampaignId])

  const loadDiscoveredContactCounts = useCallback(async () => {
    if (!authRequestsEnabled) {
      setDiscoveredContactCounts(null)
      return
    }
    if (!selectedCampaignId) {
      setDiscoveredContactCounts(null)
      return
    }
    try {
      const data = await getDiscoveredContactCounts(selectedCampaignId)
      setDiscoveredContactCounts(data)
    } catch { /* non-critical */ }
  }, [authRequestsEnabled, selectedCampaignId])

  const loadRecentActivity = useCallback(async () => {
    if (!authRequestsEnabled) {
      setRecentScrapeJobs([])
      setRecentRuns([])
      return
    }
    if (!selectedCampaignId) {
      setRecentScrapeJobs([])
      setRecentRuns([])
      return
    }
    if (uploads.length === 0) {
      setRecentScrapeJobs([])
      setRecentRuns([])
      return
    }
    try {
      const [runRows, scrapeRows] = await Promise.all([
        listRuns(selectedCampaignId ?? undefined, 50, 0),
        listScrapeJobs(selectedCampaignId, 50).catch(() => []),
      ])
      setRecentScrapeJobs(scrapeRows)
      setRecentRuns(runRows)
    } catch { /* non-critical */ }
  }, [authRequestsEnabled, selectedCampaignId, uploads])

  const loadCampaignData = useCallback(async () => {
    if (!authRequestsEnabled) {
      setCampaigns([])
      setUploads([])
      setIsCampaignLoading(false)
      return
    }
    setIsCampaignLoading(true)
    let activeCampaignId: string | null = selectedCampaignId
    try {
      const campaignRows = await listCampaigns(200, 0)
      setCampaigns(campaignRows.items)
      if (campaignRows.items.length > 0) {
        if (selectedCampaignId && campaignRows.items.some((c) => c.id === selectedCampaignId)) {
          // keep current selection
        } else {
          const pilot = campaignRows.items.find((c) => c.name.toLowerCase().includes('pilot'))
          activeCampaignId = (pilot ?? campaignRows.items[0]).id
          setSelectedCampaignIdAndCancel(activeCampaignId)
        }
      } else {
        activeCampaignId = null
        if (selectedCampaignId) setSelectedCampaignIdAndCancel(null)
      }
    } catch {
      setCampaigns([])
      activeCampaignId = null
    } finally {
      setIsCampaignLoading(false)
    }
    // Uploads loaded separately so a failure doesn't poison campaign loading
    if (activeCampaignId) {
      listUploads(activeCampaignId, 200, 0).then((r) => setUploads(r.items)).catch(() => setUploads([]))
    } else {
      setUploads([])
    }
  }, [authRequestsEnabled, selectedCampaignId, setSelectedCampaignIdAndCancel])

  const loadCampaignCostSummary = useCallback(async (campaignId: string | null) => {
    if (!authRequestsEnabled || !campaignId) {
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
  }, [authRequestsEnabled])

  const loadCampaignCostBreakdown = useCallback(async (campaignId: string | null) => {
    if (!authRequestsEnabled || !campaignId) {
      setCampaignCostBreakdown(null)
      return
    }
    try {
      const rows = await getCostStats({ campaignId, windowDays: 365, limit: 200, offset: 0 })
      setCampaignCostBreakdown(rows)
    } catch {
      setCampaignCostBreakdown(null)
    }
  }, [authRequestsEnabled])

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    configureApiSession({
      getAccessToken: () => authSession?.accessToken ?? null,
      onUnauthorized: () => {
        if (!AUTH_REQUIRED || isAuthBootstrapping) return
        setAuthSession(null)
        setAuthError('Your session expired. Please sign in again.')
      },
    })
  }, [authSession, isAuthBootstrapping])

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
    if (!authRequestsEnabled) return
    void promptMgmt.loadPrompts()
    void scrapePromptMgmt.loadScrapePrompts()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRequestsEnabled])

  useEffect(() => {
    selectedCampaignIdRef.current = selectedCampaignId
  }, [selectedCampaignId])

  useEffect(() => {
    if (!authRequestsEnabled) return
    void loadCampaignData()
  }, [authRequestsEnabled, loadCampaignData])

  useEffect(() => {
    void loadServicesHealth()
  }, [loadServicesHealth])

  useEffect(() => {
    if (!authRequestsEnabled) return
    void loadStats()
    void loadCompanyCounts()
    void loadContactCounts()
    void loadDiscoveredContactCounts()
    void loadRecentActivity()
    const timer = window.setInterval(() => {
      void loadStats()
      void loadCompanyCounts()
      void loadContactCounts()
      void loadDiscoveredContactCounts()
      void loadCampaignCostSummary(selectedCampaignId)
      void loadCampaignCostBreakdown(selectedCampaignId)
    }, 60000)
    return () => window.clearInterval(timer)
  }, [authRequestsEnabled, loadStats, loadCompanyCounts, loadContactCounts, loadDiscoveredContactCounts, loadRecentActivity, loadCampaignCostSummary, loadCampaignCostBreakdown, selectedCampaignId])

  useCampaignEventStream(
    authRequestsEnabled ? selectedCampaignId : null,
    useCallback(() => {
      void loadStats()
      void loadCompanyCounts()
      void loadContactCounts()
      void loadDiscoveredContactCounts()
      refreshPipelineView({ background: true })
    }, [loadStats, loadCompanyCounts, loadContactCounts, loadDiscoveredContactCounts, refreshPipelineView]),
    authRequestsEnabled,
  )

  useEffect(() => {
    if (!authRequestsEnabled) return
    if (!selectedCampaignId) return
    const livePipelineViews: ActiveView[] = [
      'full-pipeline',
      's1-scraping',
      's2-ai',
      's3-contacts',
      's4-reveal',
      's5-validation',
    ]
    if (!livePipelineViews.includes(activeView)) return
    const timer = window.setInterval(() => {
      refreshPipelineView({ background: true })
    }, 30000)
    return () => window.clearInterval(timer)
  }, [activeView, authRequestsEnabled, refreshPipelineView, selectedCampaignId])

  useEffect(() => {
    setCampaignCostSummary(null)
    setCampaignCostBreakdown(null)
    if (!authRequestsEnabled) {
      setLatestPipelineRunId(null)
      setLatestPipelineRunProgress(null)
      return
    }
    void loadCampaignCostSummary(selectedCampaignId)
    void loadCampaignCostBreakdown(selectedCampaignId)
    setLatestPipelineRunId(null)
    setLatestPipelineRunProgress(null)
  }, [authRequestsEnabled, loadCampaignCostBreakdown, loadCampaignCostSummary, selectedCampaignId])

  useEffect(() => {
    if (!authRequestsEnabled || !latestPipelineRunId) return
    let cancelled = false
    let timer: number | null = null
    const stopPolling = () => {
      cancelled = true
      if (timer !== null) {
        window.clearInterval(timer)
        timer = null
      }
    }
    const loadProgress = async () => {
      try {
        const progress = await getPipelineRunProgress(latestPipelineRunId)
        if (cancelled) return
        setLatestPipelineRunProgress(progress)
        void loadCampaignCostSummary(progress.campaign_id)
        void loadCampaignCostBreakdown(progress.campaign_id)
        if (progress.state === 'completed' || progress.state === 'failed') {
          setLatestPipelineRunId(null)
          stopPolling()
        }
      } catch {
        // non-critical telemetry path
      }
    }
    void loadProgress()
    timer = window.setInterval(() => {
      void loadProgress()
    }, 5000)
    return () => {
      stopPolling()
    }
  }, [authRequestsEnabled, latestPipelineRunId, loadCampaignCostSummary, loadCampaignCostBreakdown])

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

  const onUploadFromView = async (file: File, campaignId: string): Promise<{ new_count: number; dupe_count: number }> => {
    const result = await uploadFileToCampaign(file, campaignId)
    void loadCompanyCounts()
    refreshPipelineView()
    void loadRecentActivity()
    void loadCampaignData()
    return { new_count: result.new_count, dupe_count: result.dupe_count }
  }

  const onCreateCampaign = async (name: string, description: string) => {
    setIsCampaignSaving(true)
    setBusyMessage('Creating campaign…')
    setError('')
    try {
      const created = await createCampaign({ name, description })
      setSelectedCampaignIdAndCancel(created.id)
      setNotice(`Campaign "${created.name}" created.`)
      await loadCampaignData()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setBusyMessage(null)
      setIsCampaignSaving(false)
    }
  }

  const onDeleteCampaign = async (campaignId: string) => {
    setIsCampaignSaving(true)
    setBusyMessage('Deleting campaign…')
    setError('')
    try {
      await deleteCampaign(campaignId)
      if (selectedCampaignId === campaignId) {
        setSelectedCampaignIdAndCancel(null)
      }
      setNotice('Campaign deleted.')
      await loadCampaignData()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setBusyMessage(null)
      setIsCampaignSaving(false)
    }
  }


  // ── Per-row contact fetch (S3) ────────────────────────────────────────────


  const onStartCampaignPipeline = async () => {
    if (!selectedCampaignId) {
      setError('Select a campaign before starting a pipeline run.')
      return
    }
    const campaignId = selectedCampaignId
    setError('')
    setNotice('')
    setNoticeAction(null)
    setIsStartingCampaignPipeline(true)
    try {
      const result = await startPipelineRun({
        campaign_id: campaignId,
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
      if (selectedCampaignIdRef.current === campaignId) {
        setNotice(
          `Pipeline run ${result.pipeline_run_id} queued: requested ${result.requested_count}, reused ${result.reused_count}, queued ${result.queued_count}, skipped ${result.skipped_count}, failed ${result.failed_count}.`,
        )
        setLatestPipelineRunId(result.pipeline_run_id)
        void loadStats()
        void loadCompanyCounts()
        void loadRecentActivity()
        void loadCampaignData()
        void loadCampaignCostSummary(campaignId)
        refreshPipelineView()
      }
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
    setSelectedCampaignIdAndCancel(campaignId)
    syncUrlState({ view: activeView, campaignId }, 'push')
  }, [activeView, setSelectedCampaignIdAndCancel, syncUrlState])

  const requiresCampaignScope = activeView !== 'dashboard' && activeView !== 'campaigns' && activeView !== 'uploads' && activeView !== 'settings'

  const navigateToView = useCallback((view: ActiveView) => {
    const viewNeedsCampaign = view !== 'dashboard' && view !== 'campaigns' && view !== 'uploads' && view !== 'settings'
    if (viewNeedsCampaign && !selectedCampaignId) {
      setActiveViewAndCancel('campaigns')
      syncUrlState({ view: 'campaigns', campaignId: selectedCampaignId }, 'push')
      setNotice('Select a campaign first, then continue to the pipeline stage.')
      setNoticeAction({
        label: 'Open Campaigns',
        onClick: () => {
          setActiveViewAndCancel('campaigns')
        },
      })
      return
    }
    setNoticeAction(null)
    setActiveViewAndCancel(view)
    syncUrlState({ view, campaignId: selectedCampaignId }, 'push')
  }, [selectedCampaignId, setActiveViewAndCancel, syncUrlState])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const onPopState = () => {
      const routeState = parseRouteState(window.location.search)
      setActiveViewAndCancel(routeState.view)
      setSelectedCampaignIdAndCancel(routeState.campaignId)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [setActiveViewAndCancel, setSelectedCampaignIdAndCancel])

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
        campaigns={campaigns}
        selectedCampaignId={selectedCampaignId}
        onSelectCampaign={(id) => setSelectedCampaignIdAndCancel(id)}
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
            servicesHealth={servicesHealth}
            isLoadingHealth={isLoadingHealth}
            hasSelectedCampaign={Boolean(selectedCampaignId)}
            onNavigate={(view) => navigateToView(view)}
            onNavigateToUploads={() => navigateToView('uploads')}
            onOpenCampaigns={() => navigateToView('campaigns')}
            onOpenOperations={() => navigateToView('operations')}
            onOpenSettings={() => navigateToView('settings')}
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
            selectedCampaignId={selectedCampaignId}
            onSelectCampaign={(id) => setCampaignFromUser(id)}
            onNavigateToDashboard={() => navigateToView('dashboard')}
            onCreate={(name, description) => void onCreateCampaign(name, description)}
            onEdit={() => Promise.resolve()}
            onDelete={(campaignId) => void onDeleteCampaign(campaignId)}
          />
        )}

        {activeView === 'uploads' && (
          <ImportView
            campaigns={campaigns}
            selectedCampaignId={selectedCampaignId}
            uploads={uploads}
            onUpload={onUploadFromView}
            onNavigateToPipeline={() => navigateToView('s1-scraping')}
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
            statusFilter={pipeline.fullPipelineStatusFilter}
            search={pipeline.fullPipelineSearch}
            isScraping={pipeline.isFullPipelineScraping}
            isSelectingAllMatching={pipeline.isFullPipelineSelectingAllMatching}
            onSelectAllMatching={pipeline.onFullPipelineSelectAllMatching}
            onLetterChange={pipeline.onFullPipelineLetterChange}
            onStatusFilterChange={pipeline.onFullPipelineStatusFilterChange}
            onSearchChange={pipeline.onFullPipelineSearchChange}
            onToggleRow={pipeline.onFullPipelineToggleRow}
            onToggleAll={pipeline.onFullPipelineToggleAll}
            onClearSelection={pipeline.onFullPipelineClearSelection}
            onScrapeSelected={pipeline.onFullPipelineScrapeSelected}
            onStartCampaignPipeline={() => void onStartCampaignPipeline()}
            onResumeCompany={pipeline.onFullPipelineResumeCompany}
            onPagePrev={pipeline.onFullPipelinePagePrev}
            onPageNext={pipeline.onFullPipelinePageNext}
            onPageSizeChange={pipeline.onFullPipelinePageSizeChange}
            sortBy={pipeline.fullPipelineSortBy}
            sortDir={pipeline.fullPipelineSortDir}
            onSort={pipeline.onFullPipelineSort}
            isStartingCampaignPipeline={isStartingCampaignPipeline}
            latestRunProgress={latestPipelineRunProgress}
            campaignCostSummary={campaignCostSummary}
            campaignCostBreakdown={campaignCostBreakdown}
            mockFallback={!pipeline.fullPipelineCompanies}
          />
        )}

        {selectedCampaignId && activeView === 's1-scraping' && (
          <ScrapingView
            campaignId={selectedCampaignId}
            sseUrl={`/v1/campaigns/${selectedCampaignId}/events/stream`}
          />
        )}

        {selectedCampaignId && activeView === 's2-ai' && (
          <AIReviewView stats={stats} />
        )}

        {selectedCampaignId && activeView === 's3-contacts' && (
          <ContactsView stats={stats} />
        )}

        {selectedCampaignId && activeView === 's4-reveal' && (
          <S4RevealView
            contacts={pipeline.s4DiscoveredContacts}
            counts={pipeline.s4DiscoveredCounts}
            letterCounts={pipeline.s4RevealLetterCounts}
            activeLetters={pipeline.s4RevealActiveLetters}
            selectedIds={pipeline.s4DiscoveredSelectedIds}
            matchFilter={pipeline.s4MatchFilter}
            search={pipeline.s4RevealSearch}
            isSelectingAll={pipeline.isS4RevealSelectingAllMatching}
            sortBy={pipeline.s4RevealSortBy}
            sortDir={pipeline.s4RevealSortDir}
            staleEmailOnly={pipeline.s4StaleEmailOnly}
            onStaleEmailOnlyChange={pipeline.onS4StaleEmailOnlyChange}
            onMatchFilterChange={pipeline.onS4MatchFilterChange}
            onSearchChange={pipeline.onS4RevealSearchChange}
            onToggleLetter={pipeline.onS4RevealToggleLetter}
            onClearLetters={pipeline.onS4RevealClearLetters}
            onToggle={pipeline.onS4ToggleDiscovered}
            onToggleAll={pipeline.onS4ToggleAllDiscovered}
            onSelectAllMatching={pipeline.onS4RevealSelectAllMatching}
            onClearSelection={pipeline.onS4ClearDiscoveredSelection}
            onRevealSelected={pipeline.onS4RevealSelected}
            onOpenTitleRules={() => setIsTitleRulesOpen(true)}
            offset={pipeline.s4RevealOffset}
            pageSize={pipeline.s4RevealPageSize}
            onPagePrev={pipeline.onS4RevealPagePrev}
            onPageNext={pipeline.onS4RevealPageNext}
            onPageSizeChange={pipeline.onS4RevealPageSizeChange}
            onSort={pipeline.onS4RevealSort}
            isLoading={pipeline.isS4RevealLoading}
            isRevealing={pipeline.isS4Revealing}
          />
        )}

        {selectedCampaignId && activeView === 's5-validation' && (
          <ValidationView stats={stats} />
        )}

        {activeView === 'queue-history' && (
          <QueueHistoryView campaignId={selectedCampaignId} />
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
        newRulesSinceLastSeen={titleRulesNewCountAtOpen}
        onClose={() => {
          setIsTitleRulesOpen(false)
          setTitleRulesNewCountAtOpen(0)
        }}
      />

      {busyMessage !== null && <GlobalLoadingOverlay message={busyMessage} />}
    </>
  )
}

export default App
