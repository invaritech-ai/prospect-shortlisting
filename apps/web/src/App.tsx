import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  createRuns,
  createPrompt,
  createScrapeJob,
  deleteCompanies,
  drainQueue,
  enqueueRunAll,
  fetchContactsForCompany,
  fetchContactsForRun,
  getAnalysisJobDetail,
  getCompaniesExportUrl,
  getCompanyCounts,
  getLetterCounts,
  getStats,
  listCompanies,
  listCompanyIds,
  listPrompts,
  listRunJobs,
  listRuns,
  listScrapeJobPageContents,
  listScrapeJobs,
  resetStuckJobs,
  resetStuckAnalysisJobs,
  scrapeAllCompanies,
  scrapeSelectedCompanies,
  updatePrompt,
  uploadFile,
  upsertCompanyFeedback,
} from './lib/api'
import type {
  AnalyticsSnapshot,
  AnalysisJobDetailRead,
  AnalysisRunJobRead,
  CompanyCounts,
  CompanyList,
  CompanyListItem,
  DecisionFilter,
  ManualLabel,
  PromptRead,
  RunRead,
  ScrapeFilter,
  ScrapeJobRead,
  ScrapePageContentRead,
  StatsResponse,
} from './lib/types'
import type { ActiveView } from './lib/navigation'
import {
  buildAnalyticsSnapshot,
  buildOperationsEvents,
  runStatus,
  scrapeStatus,
  topFailedRunPrompts,
  topScrapeErrorCodes,
  type CountBucket,
} from './lib/telemetry'

// Layout & views
import { AppShell } from './components/layout/AppShell'
import { CompaniesView } from './components/views/CompaniesView'
import { ScrapeJobsView } from './components/views/ScrapeJobsView'
import { AnalysisRunsView } from './components/views/AnalysisRunsView'
import { OperationsLogView } from './components/views/OperationsLogView'
import { AnalyticsSnapshotView } from './components/views/AnalyticsSnapshotView'
import { ContactsView } from './components/views/ContactsView'

// Panels
import { MarkdownPreviewPanel } from './components/panels/MarkdownPreviewPanel'
import { PromptLibraryPanel } from './components/panels/PromptLibraryPanel'
import { AnalysisDetailPanel } from './components/panels/AnalysisDetailPanel'
import { CompanyReviewPanel } from './components/panels/CompanyReviewPanel'
import { ScrapeDiagnosticsPanel } from './components/panels/ScrapeDiagnosticsPanel'

// UI
import { Toast } from './components/ui/Toast'

// ── Constants ──────────────────────────────────────────────────────────────

const DEFAULT_COMPANY_PAGE_SIZE = 100
const DEFAULT_JOBS_PAGE_SIZE = 50
const DEFAULT_RUNS_PAGE_SIZE = 25
const DEFAULT_OPERATIONS_LIMIT = 100
const DEFAULT_ANALYTICS_SAMPLE_LIMIT = 120
const PROMPT_SELECTION_KEY = 'ps:selected-prompt-id'
const MAX_POLL_FAILURES = 3

type JobFilter = 'all' | 'active' | 'completed' | 'failed'

// ── App ────────────────────────────────────────────────────────────────────

function App() {
  // ── Refs ────────────────────────────────────────────────────────────────
  const companyCacheRef = useRef<Record<string, CompanyList>>({})
  const pollFailuresRef = useRef(0)
  const editingPromptIdRef = useRef<string | null>(null)
  const selectedPromptIdRef = useRef('')

  // ── Navigation ──────────────────────────────────────────────────────────
  const [activeView, setActiveView] = useState<ActiveView>('companies')

  // ── Companies ───────────────────────────────────────────────────────────
  const [companies, setCompanies] = useState<CompanyList | null>(null)
  const [companyOffset, setCompanyOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_COMPANY_PAGE_SIZE)
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>('all')
  const [scrapeFilter, setScrapeFilter] = useState<ScrapeFilter>('all')
  const [letterFilter, setLetterFilter] = useState<string | null>(null)
  const [letterCounts, setLetterCounts] = useState<Record<string, number>>({})
  const [isCompaniesLoading, setIsCompaniesLoading] = useState(false)
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<string[]>([])
  const [companyCounts, setCompanyCounts] = useState<CompanyCounts | null>(null)
  const [actionState, setActionState] = useState<Record<string, string>>({})
  const [analysisActionState, setAnalysisActionState] = useState<Record<string, string>>({})

  // ── Upload ───────────────────────────────────────────────────────────────
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isDragActive, setIsDragActive] = useState(false)
  const [utilitiesOpen, setUtilitiesOpen] = useState(false)

  // ── Bulk actions ─────────────────────────────────────────────────────────
  const [isDeleting, setIsDeleting] = useState(false)
  const [isScrapingSelected, setIsScrapingSelected] = useState(false)
  const [isScrapingAll, setIsScrapingAll] = useState(false)
  const [isClassifyingSelected, setIsClassifyingSelected] = useState(false)
  const [isClassifyingAll, setIsClassifyingAll] = useState(false)
  const [isSelectingAll, setIsSelectingAll] = useState(false)
  const [isFetchingContactsSelected, setIsFetchingContactsSelected] = useState(false)

  // ── Scrape jobs ──────────────────────────────────────────────────────────
  const [scrapeJobs, setScrapeJobs] = useState<ScrapeJobRead[]>([])
  const [jobsOffset, setJobsOffset] = useState(0)
  const [jobsPageSize, setJobsPageSize] = useState(DEFAULT_JOBS_PAGE_SIZE)
  const [jobsFilter, setJobsFilter] = useState<JobFilter>('all')
  const [isJobsLoading, setIsJobsLoading] = useState(false)
  const [jobsHasMore, setJobsHasMore] = useState(false)

  // ── Analysis runs ────────────────────────────────────────────────────────
  const [runs, setRuns] = useState<RunRead[]>([])
  const [runsOffset, setRunsOffset] = useState(0)
  const [runsPageSize, setRunsPageSize] = useState(DEFAULT_RUNS_PAGE_SIZE)
  const [isRunsLoading, setIsRunsLoading] = useState(false)
  const [runsHasMore, setRunsHasMore] = useState(false)

  // ── Operations log snapshot ──────────────────────────────────────────────
  const [operationsScrapeJobs, setOperationsScrapeJobs] = useState<ScrapeJobRead[]>([])
  const [operationsRuns, setOperationsRuns] = useState<RunRead[]>([])
  const [operationsPipelineFilter, setOperationsPipelineFilter] = useState<'all' | 'scrape' | 'analysis'>('all')
  const [operationsStatusFilter, setOperationsStatusFilter] = useState<'all' | 'active' | 'completed' | 'failed'>('all')
  const [operationsErrorOnly, setOperationsErrorOnly] = useState(false)
  const [operationsSearchQuery, setOperationsSearchQuery] = useState('')
  const [isOperationsLoading, setIsOperationsLoading] = useState(false)
  const [operationsError, setOperationsError] = useState('')

  // ── Analytics snapshot ───────────────────────────────────────────────────
  const [analyticsScrapeSample, setAnalyticsScrapeSample] = useState<ScrapeJobRead[]>([])
  const [analyticsRunSample, setAnalyticsRunSample] = useState<RunRead[]>([])
  const [isAnalyticsLoading, setIsAnalyticsLoading] = useState(false)
  const [analyticsError, setAnalyticsError] = useState('')

  // ── Analysis detail panel ────────────────────────────────────────────────
  const [inspectedRun, setInspectedRun] = useState<RunRead | null>(null)
  const [runJobs, setRunJobs] = useState<AnalysisRunJobRead[]>([])
  const [isRunJobsLoading, setIsRunJobsLoading] = useState(false)
  const [runJobsError, setRunJobsError] = useState('')
  const [analysisDetail, setAnalysisDetail] = useState<AnalysisJobDetailRead | null>(null)
  const [isAnalysisDetailLoading, setIsAnalysisDetailLoading] = useState(false)
  const [analysisDetailError, setAnalysisDetailError] = useState('')

  // ── Company review panel ──────────────────────────────────────────────────
  const [reviewedCompany, setReviewedCompany] = useState<CompanyListItem | null>(null)
  const [companyReviewDetail, setCompanyReviewDetail] = useState<AnalysisJobDetailRead | null>(null)
  const [isCompanyReviewLoading, setIsCompanyReviewLoading] = useState(false)
  const [companyReviewError, setCompanyReviewError] = useState('')
  const [isFeedbackSaving, setIsFeedbackSaving] = useState(false)

  // ── Markdown panel ───────────────────────────────────────────────────────
  const [markdownJob, setMarkdownJob] = useState<ScrapeJobRead | null>(null)
  const [markdownPages, setMarkdownPages] = useState<ScrapePageContentRead[]>([])
  const [activeMarkdownPageKind, setActiveMarkdownPageKind] = useState<string>('')
  const [isMarkdownLoading, setIsMarkdownLoading] = useState(false)
  const [markdownError, setMarkdownError] = useState('')
  const [markdownCopyState, setMarkdownCopyState] = useState('')

  // ── Scrape diagnostics panel ─────────────────────────────────────────────
  const [diagnosticsJob, setDiagnosticsJob] = useState<ScrapeJobRead | null>(null)
  const [diagnosticsPages, setDiagnosticsPages] = useState<ScrapePageContentRead[]>([])
  const [isDiagnosticsLoading, setIsDiagnosticsLoading] = useState(false)
  const [diagnosticsError, setDiagnosticsError] = useState('')

  // ── Prompts ──────────────────────────────────────────────────────────────
  const [prompts, setPrompts] = useState<PromptRead[]>([])
  const [selectedPromptId, setSelectedPromptIdState] = useState('')
  const setSelectedPromptId = (v: string) => {
    selectedPromptIdRef.current = v
    setSelectedPromptIdState(v)
  }
  const [editingPromptId, setEditingPromptIdState] = useState<string | null>(null)
  const setEditingPromptId = (v: string | null) => {
    editingPromptIdRef.current = v
    setEditingPromptIdState(v)
  }
  const [promptName, setPromptName] = useState('')
  const [promptText, setPromptText] = useState('')
  const [promptEnabled, setPromptEnabled] = useState(true)
  const [isPromptsLoading, setIsPromptsLoading] = useState(false)
  const [isPromptSaving, setIsPromptSaving] = useState(false)
  const [promptError, setPromptError] = useState('')
  const [promptSheetOpen, setPromptSheetOpen] = useState(false)

  // ── Pipeline stats ───────────────────────────────────────────────────────
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [isDrainingQueue, setIsDrainingQueue] = useState(false)
  const [isResettingStuck, setIsResettingStuck] = useState(false)
  const [isResettingStuckAnalysis, setIsResettingStuckAnalysis] = useState(false)

  // ── Toasts ───────────────────────────────────────────────────────────────
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // ── Error parsing ─────────────────────────────────────────────────────────
  const parseError = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (typeof err.detail === 'string') return err.detail
      if (typeof err.detail === 'object' && err.detail !== null && 'message' in err.detail) {
        return (err.detail as { message: string }).message
      }
      if (Array.isArray(err.detail)) return JSON.stringify(err.detail)
      return JSON.stringify(err.detail)
    }
    if (err instanceof Error) return err.message
    return 'Unknown error'
  }

  // ── Company loading ────────────────────────────────────────────────────

  const cacheKeyFor = useCallback(
    (offset: number, limit: number, df: DecisionFilter, sf: ScrapeFilter, lf: string | null = null) =>
      `${df}:${sf}:${lf ?? ''}:${limit}:${offset}`,
    [],
  )

  const prefetchCompanies = useCallback(
    async (offset: number, limit: number, df: DecisionFilter, sf: ScrapeFilter, lf: string | null = null) => {
      const key = cacheKeyFor(offset, limit, df, sf, lf)
      if (companyCacheRef.current[key]) return
      try {
        const response = await listCompanies(limit, offset, df, false, sf, lf)
        companyCacheRef.current[key] = response
      } catch { /* silent */ }
    },
    [cacheKeyFor],
  )

  const loadCompanies = useCallback(
    async (
      offset = 0,
      nextLimit = pageSize,
      df: DecisionFilter = decisionFilter,
      sf: ScrapeFilter = scrapeFilter,
      forceRefresh = false,
      lf: string | null = letterFilter,
    ) => {
      const key = cacheKeyFor(offset, nextLimit, df, sf, lf)
      const cached = companyCacheRef.current[key]
      if (cached && !forceRefresh) {
        setCompanies(cached)
        setCompanyOffset(offset)
        void prefetchCompanies(offset + nextLimit, nextLimit, df, sf, lf)
        return
      }
      setIsCompaniesLoading(true)
      try {
        const response = await listCompanies(nextLimit, offset, df, false, sf, lf)
        companyCacheRef.current[key] = response
        setCompanies(response)
        setCompanyOffset(offset)
        pollFailuresRef.current = 0
        if (response.has_more) void prefetchCompanies(offset + nextLimit, nextLimit, df, sf, lf)
      } catch (err) {
        setError(parseError(err))
      } finally {
        setIsCompaniesLoading(false)
      }
    },
    [cacheKeyFor, decisionFilter, scrapeFilter, letterFilter, pageSize, prefetchCompanies],
  )

  const loadScrapeJobs = useCallback(
    async (offset = 0, limit = jobsPageSize) => {
      setIsJobsLoading(true)
      try {
        const rows = await listScrapeJobs(limit + 1, offset, jobsFilter)
        setJobsHasMore(rows.length > limit)
        setScrapeJobs(rows.slice(0, limit))
        setJobsOffset(offset)
      } catch (err) {
        setError(parseError(err))
      } finally {
        setIsJobsLoading(false)
      }
    },
    [jobsFilter, jobsPageSize],
  )

  const loadRuns = useCallback(
    async (offset = 0, limit = runsPageSize) => {
      setIsRunsLoading(true)
      try {
        const rows = await listRuns(limit + 1, offset)
        setRunsHasMore(rows.length > limit)
        setRuns(rows.slice(0, limit))
        setRunsOffset(offset)
      } catch (err) {
        setError(parseError(err))
      } finally {
        setIsRunsLoading(false)
      }
    },
    [runsPageSize],
  )

  const loadOperationsSnapshot = useCallback(async () => {
    setIsOperationsLoading(true)
    setOperationsError('')
    try {
      const [scrapeRows, runRows] = await Promise.all([
        listScrapeJobs(DEFAULT_OPERATIONS_LIMIT, 0, operationsStatusFilter),
        listRuns(DEFAULT_OPERATIONS_LIMIT, 0),
      ])
      setOperationsScrapeJobs(scrapeRows)
      setOperationsRuns(
        operationsStatusFilter === 'all'
          ? runRows
          : runRows.filter((row) => runStatus(row) === operationsStatusFilter),
      )
    } catch (err) {
      setOperationsError(parseError(err))
    } finally {
      setIsOperationsLoading(false)
    }
  }, [operationsStatusFilter])

  const loadAnalyticsSnapshot = useCallback(async () => {
    setIsAnalyticsLoading(true)
    setAnalyticsError('')
    try {
      const [scrapeRows, runRows, statsResponse, companyCountsResponse] = await Promise.all([
        listScrapeJobs(DEFAULT_ANALYTICS_SAMPLE_LIMIT, 0, 'all'),
        listRuns(DEFAULT_ANALYTICS_SAMPLE_LIMIT, 0),
        getStats(),
        getCompanyCounts(),
      ])
      setAnalyticsScrapeSample(scrapeRows)
      setAnalyticsRunSample(runRows)
      setStats(statsResponse)
      setCompanyCounts(companyCountsResponse)
    } catch (err) {
      setAnalyticsError(parseError(err))
    } finally {
      setIsAnalyticsLoading(false)
    }
  }, [])

  const loadRunJobs = useCallback(async (run: RunRead) => {
    setInspectedRun(run)
    setRunJobs([])
    setAnalysisDetail(null)
    setRunJobsError('')
    setAnalysisDetailError('')
    setIsRunJobsLoading(true)
    try {
      const rows = await listRunJobs(run.id)
      setRunJobs(rows)
    } catch (err) {
      setRunJobsError(parseError(err))
    } finally {
      setIsRunJobsLoading(false)
    }
  }, [])

  const loadPrompts = useCallback(
    async (preferredPromptId?: string, preserveEditor = false) => {
      setIsPromptsLoading(true)
      try {
        const rows = await listPrompts()
        setPrompts(rows)
        setPromptError('')
        const stored = window.localStorage.getItem(PROMPT_SELECTION_KEY) ?? ''
        const preferredId =
          (preferredPromptId && rows.find((p) => p.id === preferredPromptId && p.enabled)?.id) ||
          (selectedPromptIdRef.current && rows.find((p) => p.id === selectedPromptIdRef.current && p.enabled)?.id) ||
          rows.find((p) => p.id === stored && p.enabled)?.id ||
          rows.find((p) => p.enabled)?.id ||
          rows[0]?.id || ''
        setSelectedPromptId(preferredId)
        if (preferredId) window.localStorage.setItem(PROMPT_SELECTION_KEY, preferredId)
        else window.localStorage.removeItem(PROMPT_SELECTION_KEY)

        if (!preserveEditor) {
          const forEditor =
            rows.find((p) => p.id === (preferredPromptId || editingPromptIdRef.current || preferredId)) ??
            rows[0] ?? null
          if (forEditor) {
            setEditingPromptId(forEditor.id)
            setPromptName(forEditor.name)
            setPromptText(forEditor.prompt_text)
            setPromptEnabled(forEditor.enabled)
          } else {
            setEditingPromptId(null)
            setPromptName('')
            setPromptText('')
            setPromptEnabled(true)
          }
        }
      } catch (err) {
        setPromptError(parseError(err))
      } finally {
        setIsPromptsLoading(false)
      }
    },
    [],
  )

  const loadStats = useCallback(async () => {
    if (pollFailuresRef.current >= MAX_POLL_FAILURES) return
    try {
      const data = await getStats()
      setStats(data)
      pollFailuresRef.current = 0
    } catch {
      pollFailuresRef.current += 1
    }
  }, [])

  const loadCompanyCounts = useCallback(async () => {
    try {
      const data = await getCompanyCounts()
      setCompanyCounts(data)
    } catch { /* non-critical */ }
  }, [])

  const loadLetterCounts = useCallback(async (df: DecisionFilter, sf: ScrapeFilter) => {
    try {
      const data = await getLetterCounts(df, sf)
      setLetterCounts(data.counts)
    } catch { /* non-critical */ }
  }, [])

  // ── Effects ────────────────────────────────────────────────────────────

  useEffect(() => {
    setSelectedCompanyIds([])
    setCompanyOffset(0)
    companyCacheRef.current = {}
    void loadCompanies(0, pageSize, decisionFilter, scrapeFilter)
  }, [decisionFilter, scrapeFilter, letterFilter, loadCompanies, pageSize])

  useEffect(() => {
    void loadLetterCounts(decisionFilter, scrapeFilter)
  }, [decisionFilter, scrapeFilter, loadLetterCounts])

  useEffect(() => { void loadScrapeJobs(0, jobsPageSize) }, [jobsFilter, jobsPageSize, loadScrapeJobs])
  useEffect(() => { void loadRuns(0, runsPageSize) }, [runsPageSize, loadRuns])
  useEffect(() => { void loadPrompts() }, [loadPrompts])

  useEffect(() => {
    if (activeView !== 'operations') return
    void loadOperationsSnapshot()
  }, [activeView, loadOperationsSnapshot])

  useEffect(() => {
    if (activeView !== 'operations') return
    const hasActiveOps =
      operationsScrapeJobs.some((job) => scrapeStatus(job) === 'active') ||
      operationsRuns.some((run) => runStatus(run) === 'active')
    const cadenceMs = hasActiveOps ? 4000 : 10000
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'hidden') return
      void loadOperationsSnapshot()
    }, cadenceMs)
    return () => window.clearInterval(timer)
  }, [activeView, loadOperationsSnapshot, operationsScrapeJobs, operationsRuns])

  useEffect(() => {
    if (activeView !== 'analytics') return
    void loadAnalyticsSnapshot()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'hidden') return
      void loadAnalyticsSnapshot()
    }, 10000)
    return () => window.clearInterval(timer)
  }, [activeView, loadAnalyticsSnapshot])

  useEffect(() => {
    void loadStats()
    void loadCompanyCounts()
    const timer = window.setInterval(() => {
      void loadStats()
      void loadCompanyCounts()
    }, 10000)
    return () => window.clearInterval(timer)
  }, [loadStats, loadCompanyCounts])

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

  useEffect(() => {
    const hasActive = scrapeJobs.some((j) => !j.terminal_state)
    if (!hasActive) return
    const timer = window.setInterval(() => void loadScrapeJobs(jobsOffset, jobsPageSize), 4000)
    return () => window.clearInterval(timer)
  }, [jobsOffset, jobsPageSize, loadScrapeJobs, scrapeJobs])

  useEffect(() => {
    const hasActive = runs.some((r) => r.status === 'running' || r.status === 'created')
    if (!hasActive) return
    const timer = window.setInterval(() => {
      if (pollFailuresRef.current >= MAX_POLL_FAILURES) return
      void loadRuns(runsOffset, runsPageSize)
      void loadCompanies(companyOffset, pageSize, decisionFilter, scrapeFilter, true)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [companyOffset, decisionFilter, scrapeFilter, loadCompanies, loadRuns, pageSize, runs, runsOffset, runsPageSize])

  useEffect(() => {
    if (!selectedPromptId) return
    window.localStorage.setItem(PROMPT_SELECTION_KEY, selectedPromptId)
  }, [selectedPromptId])

  // ── Event handlers ─────────────────────────────────────────────────────

  const onUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!file) { setError('Choose a file first.'); return }
    setError(''); setNotice(''); setIsUploading(true)
    try {
      await uploadFile(file)
      companyCacheRef.current = {}
      setFile(null)
      setSelectedCompanyIds([])
      await loadCompanies(0, pageSize, decisionFilter)
      void loadCompanyCounts()
      setNotice('Upload parsed and companies refreshed.')
    } catch (err) { setError(parseError(err)) }
    finally { setIsUploading(false) }
  }

  const onScrape = async (company: CompanyListItem) => {
    if (company.latest_scrape_terminal === false) {
      setNotice(`Scrape already active for ${company.domain}.`); return
    }
    setError(''); setNotice('')
    setActionState((c) => ({ ...c, [company.id]: 'Creating scrape job…' }))
    try {
      const job = await createScrapeJob({ website_url: company.normalized_url })
      await enqueueRunAll(job.id)
      companyCacheRef.current = {}
      await loadCompanies(companyOffset, pageSize, decisionFilter)
      await loadScrapeJobs(0, jobsPageSize)
      setActionState((c) => ({ ...c, [company.id]: 'Queued' }))
    } catch (err) {
      setActionState((c) => ({ ...c, [company.id]: 'Failed' }))
      setError(parseError(err))
    }
  }

  const toggleCompanySelection = (id: string) => {
    setSelectedCompanyIds((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id],
    )
  }

  const toggleVisibleSelection = () => {
    if (!companies) return
    const visibleIds = companies.items.map((c) => c.id)
    const allSelected = visibleIds.every((id) => selectedCompanyIds.includes(id))
    setSelectedCompanyIds((cur) =>
      allSelected
        ? cur.filter((id) => !visibleIds.includes(id))
        : Array.from(new Set([...cur, ...visibleIds])),
    )
  }

  const onSelectAllFiltered = async () => {
    setIsSelectingAll(true)
    try {
      const result = await listCompanyIds(decisionFilter, scrapeFilter, letterFilter)
      setSelectedCompanyIds(result.ids)
    } catch (err) { setError(parseError(err)) }
    finally { setIsSelectingAll(false) }
  }

  const onDeleteSelected = async () => {
    if (selectedCompanyIds.length === 0) return
    const ok = window.confirm(
      `Permanently delete ${selectedCompanyIds.length} compan${selectedCompanyIds.length === 1 ? 'y' : 'ies'}? This cannot be undone.`,
    )
    if (!ok) return
    setError(''); setNotice(''); setIsDeleting(true)
    try {
      await deleteCompanies(selectedCompanyIds)
      companyCacheRef.current = {}
      const nextOffset =
        companies && companies.items.length === selectedCompanyIds.length && companyOffset > 0
          ? Math.max(companyOffset - (companies?.limit ?? pageSize), 0) : companyOffset
      setSelectedCompanyIds([])
      await loadCompanies(nextOffset, pageSize, decisionFilter)
      void loadCompanyCounts()
      setNotice(`Deleted ${selectedCompanyIds.length} companies.`)
    } catch (err) { setError(parseError(err)) }
    finally { setIsDeleting(false) }
  }

  const onScrapeSelected = async () => {
    if (selectedCompanyIds.length === 0) return
    setError(''); setNotice(''); setIsScrapingSelected(true)
    try {
      const result = await scrapeSelectedCompanies(selectedCompanyIds)
      companyCacheRef.current = {}
      await loadCompanies(companyOffset, pageSize, decisionFilter)
      await loadScrapeJobs(0, jobsPageSize)
      const msg = `Queued ${result.queued_count}/${result.requested_count} selected companies for scraping.`
      if (result.failed_company_ids.length > 0) setError(`${msg} ${result.failed_company_ids.length} failed.`)
      else setNotice(msg)
      setActionState((cur) => {
        const next = { ...cur }
        const failed = new Set(result.failed_company_ids)
        for (const id of selectedCompanyIds) next[id] = failed.has(id) ? 'Skipped' : 'Queued'
        return next
      })
    } catch (err) { setError(parseError(err)) }
    finally { setIsScrapingSelected(false) }
  }

  const onScrapeAll = async () => {
    setError(''); setNotice(''); setIsScrapingAll(true)
    try {
      const result = await scrapeAllCompanies()
      companyCacheRef.current = {}
      await loadCompanies(0, pageSize, decisionFilter)
      await loadScrapeJobs(0, jobsPageSize)
      void loadCompanyCounts()
      setSelectedCompanyIds([])
      const msg = `Queued ${result.queued_count}/${result.requested_count} companies for scraping.`
      if (result.failed_company_ids.length > 0) setError(`${msg} ${result.failed_company_ids.length} failed.`)
      else setNotice(msg)
    } catch (err) { setError(parseError(err)) }
    finally { setIsScrapingAll(false) }
  }

  const startClassification = async (scope: 'all' | 'selected', companyIds: string[] = []) => {
    if (!selectedPrompt?.enabled) {
      setError('Select an enabled prompt before starting classification.')
      return
    }
    setError(''); setNotice('')
    if (scope === 'all') setIsClassifyingAll(true)
    else setIsClassifyingSelected(true)
    try {
      const result = await createRuns({
        prompt_id: selectedPrompt.id,
        scope,
        company_ids: scope === 'selected' ? companyIds : undefined,
      })
      await loadRuns(0, runsPageSize)
      await loadCompanies(companyOffset, pageSize, decisionFilter, scrapeFilter, true)
      void loadCompanyCounts()
      const runCount = result.runs.length
      const msg = `Created ${runCount} run${runCount === 1 ? '' : 's'} and queued ${result.queued_count}/${result.requested_count} classifications.`
      setNotice(result.skipped_company_ids.length > 0 ? `${msg} Skipped ${result.skipped_company_ids.length} without markdown.` : msg)
      if (scope === 'selected') {
        setAnalysisActionState((cur) => {
          const next = { ...cur }
          const skipped = new Set(result.skipped_company_ids)
          for (const id of companyIds) next[id] = skipped.has(id) ? 'Skipped' : 'Queued'
          return next
        })
      }
    } catch (err) { setError(parseError(err)) }
    finally {
      if (scope === 'all') setIsClassifyingAll(false)
      else setIsClassifyingSelected(false)
    }
  }

  const onClassify = async (company: CompanyListItem) => {
    setAnalysisActionState((c) => ({ ...c, [company.id]: 'Queuing…' }))
    await startClassification('selected', [company.id])
  }

  const onClassifySelected = async () => {
    if (selectedCompanyIds.length === 0) return
    setAnalysisActionState((c) => {
      const next = { ...c }
      for (const id of selectedCompanyIds) next[id] = 'Queuing…'
      return next
    })
    await startClassification('selected', selectedCompanyIds)
  }

  // Scrape diagnostics
  const openScrapeDiagnostics = async (job: ScrapeJobRead) => {
    setDiagnosticsJob(job)
    setDiagnosticsPages([])
    setDiagnosticsError('')
    setIsDiagnosticsLoading(true)
    try {
      const pages = await listScrapeJobPageContents(job.id)
      setDiagnosticsPages(pages)
    } catch (err) {
      setDiagnosticsError(parseError(err))
    } finally {
      setIsDiagnosticsLoading(false)
    }
  }

  const closeScrapeDiagnostics = () => {
    setDiagnosticsJob(null)
    setDiagnosticsPages([])
    setDiagnosticsError('')
  }

  // Markdown panel
  const openMarkdownDrawer = async (job: ScrapeJobRead) => {
    setMarkdownJob(job)
    setMarkdownPages([]); setActiveMarkdownPageKind(''); setMarkdownError(''); setMarkdownCopyState('')
    setIsMarkdownLoading(true)
    try {
      const pages = await listScrapeJobPageContents(job.id)
      const PAGE_KIND_ORDER = ['home', 'about', 'products'] as const
      const filtered = PAGE_KIND_ORDER
        .map((kind) => pages.find((p) => p.page_kind === kind && p.markdown_content.trim().length > 0))
        .filter((p): p is ScrapePageContentRead => !!p)
      setMarkdownPages(filtered)
      setActiveMarkdownPageKind(filtered[0]?.page_kind ?? '')
      if (filtered.length === 0) setMarkdownError('No markdown available for this scrape job.')
    } catch (err) { setMarkdownError(parseError(err)) }
    finally { setIsMarkdownLoading(false) }
  }

  const closeMarkdownDrawer = () => {
    setMarkdownJob(null); setMarkdownPages([]); setActiveMarkdownPageKind('')
    setMarkdownError(''); setMarkdownCopyState('')
  }

  const copyMarkdown = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setMarkdownCopyState('Copied')
    } catch {
      setMarkdownCopyState('Copy failed')
    }
    window.setTimeout(() => setMarkdownCopyState(''), 1600)
  }

  // Prompt library
  const openPromptSheet = () => {
    setPromptSheetOpen(true)
    if (prompts.length === 0) void loadPrompts()
  }

  const closePromptSheet = () => { setPromptSheetOpen(false); setPromptError('') }

  const onSelectPrompt = (prompt: PromptRead) => {
    setSelectedPromptId(prompt.id)
    setEditingPromptId(prompt.id)
    setPromptName(prompt.name)
    setPromptText(prompt.prompt_text)
    setPromptEnabled(prompt.enabled)
  }

  const onNewPrompt = () => {
    setEditingPromptId(null); setPromptName(''); setPromptText(''); setPromptEnabled(true); setPromptError('')
  }

  const onSavePromptAsNew = async () => {
    if (!promptName.trim() || !promptText.trim()) { setPromptError('Name and prompt text are required.'); return }
    setIsPromptSaving(true)
    try {
      const created = await createPrompt({ name: promptName.trim(), prompt_text: promptText.trim(), enabled: promptEnabled })
      await loadPrompts(created.id)
      setNotice(`Prompt "${created.name}" created.`); setError('')
    } catch (err) { setPromptError(parseError(err)) }
    finally { setIsPromptSaving(false) }
  }

  const onUpdateCurrentPrompt = async () => {
    if (!editingPromptId) { setPromptError('Select an existing prompt to update.'); return }
    if (!promptName.trim() || !promptText.trim()) { setPromptError('Name and prompt text are required.'); return }
    setIsPromptSaving(true)
    try {
      const updated = await updatePrompt(editingPromptId, { name: promptName.trim(), prompt_text: promptText.trim(), enabled: promptEnabled })
      await loadPrompts(updated.id)
      setNotice(`Prompt "${updated.name}" updated.`); setError('')
    } catch (err) { setPromptError(parseError(err)) }
    finally { setIsPromptSaving(false) }
  }

  const onTogglePromptEnabled = async (prompt: PromptRead) => {
    setIsPromptSaving(true)
    try {
      const updated = await updatePrompt(prompt.id, { enabled: !prompt.enabled })
      await loadPrompts(updated.id, editingPromptId !== updated.id)
      if (editingPromptId === updated.id) setPromptEnabled(updated.enabled)
    } catch (err) { setPromptError(parseError(err)) }
    finally { setIsPromptSaving(false) }
  }

  // Analysis detail
  const openAnalysisDetail = async (job: AnalysisRunJobRead) => {
    setAnalysisDetail(null); setAnalysisDetailError(''); setIsAnalysisDetailLoading(true)
    try {
      const detail = await getAnalysisJobDetail(job.analysis_job_id)
      setAnalysisDetail(detail)
    } catch (err) { setAnalysisDetailError(parseError(err)) }
    finally { setIsAnalysisDetailLoading(false) }
  }

  const closeRunDrawer = () => {
    setInspectedRun(null); setRunJobs([]); setAnalysisDetail(null)
    setRunJobsError(''); setAnalysisDetailError('')
  }

  // Company review
  const openCompanyReview = async (company: CompanyListItem) => {
    setReviewedCompany(company)
    setCompanyReviewDetail(null)
    setCompanyReviewError('')
    if (company.latest_analysis_job_id) {
      setIsCompanyReviewLoading(true)
      try {
        const detail = await getAnalysisJobDetail(company.latest_analysis_job_id)
        setCompanyReviewDetail(detail)
      } catch (err) { setCompanyReviewError(parseError(err)) }
      finally { setIsCompanyReviewLoading(false) }
    }
  }

  const closeCompanyReview = () => {
    setReviewedCompany(null)
    setCompanyReviewDetail(null)
    setCompanyReviewError('')
  }

  const saveFeedback = async (thumbs: 'up' | 'down' | null, comment: string) => {
    if (!reviewedCompany) return
    setIsFeedbackSaving(true)
    try {
      await upsertCompanyFeedback(reviewedCompany.id, { thumbs, comment: comment || null, manual_label: reviewedCompany.feedback_manual_label ?? null })
      companyCacheRef.current = {}
      void loadCompanies(companyOffset, pageSize, decisionFilter, scrapeFilter, true)
      setReviewedCompany((prev) => prev ? { ...prev, feedback_thumbs: thumbs, feedback_comment: comment || null } : prev)
      setNotice('Feedback saved.')
    } catch (err) { setError(parseError(err)) }
    finally { setIsFeedbackSaving(false) }
  }

  const setManualLabel = async (company: CompanyListItem, label: ManualLabel | null) => {
    try {
      await upsertCompanyFeedback(company.id, { manual_label: label })
      companyCacheRef.current = {}
      void loadCompanies(companyOffset, pageSize, decisionFilter, scrapeFilter, true)
    } catch (err) { setError(parseError(err)) }
  }

  const onDrainQueue = async () => {
    if (!window.confirm('Cancel all queued jobs? This removes them from Redis and marks them as cancelled.')) return
    setError(''); setNotice(''); setIsDrainingQueue(true)
    try {
      const result = await drainQueue()
      await Promise.all([loadScrapeJobs(0, jobsPageSize), loadStats()])
      setNotice(`Drained ${result.drained.toLocaleString()} tasks from queue and cancelled ${result.cancelled_db_jobs.toLocaleString()} jobs.`)
    } catch (err) { setError(parseError(err)) }
    finally { setIsDrainingQueue(false) }
  }

  const onResetStuck = async () => {
    setError(''); setNotice(''); setIsResettingStuck(true)
    try {
      const result = await resetStuckJobs()
      await Promise.all([loadScrapeJobs(0, jobsPageSize), loadStats()])
      setNotice(`Reset and re-queued ${result.reset_count.toLocaleString()} stuck scrape jobs.`)
    } catch (err) { setError(parseError(err)) }
    finally { setIsResettingStuck(false) }
  }

  const onResetStuckAnalysis = async () => {
    setError(''); setNotice(''); setIsResettingStuckAnalysis(true)
    try {
      const result = await resetStuckAnalysisJobs()
      await Promise.all([
        loadCompanies(companyOffset, pageSize, decisionFilter, scrapeFilter, true),
        loadRuns(0, runsPageSize),
        loadStats(),
      ])
      setNotice(`Reset and re-queued ${result.reset_count.toLocaleString()} stuck analysis jobs.`)
    } catch (err) { setError(parseError(err)) }
    finally { setIsResettingStuckAnalysis(false) }
  }

  const onFetchContacts = async (company: CompanyListItem) => {
    setError(''); setNotice('')
    try {
      const result = await fetchContactsForCompany(company.id)
      const msg = result.queued_count > 0
        ? `Queued contact fetch for ${company.domain}.`
        : result.already_fetching_count > 0
          ? `Contact fetch already in progress for ${company.domain}.`
          : `No contacts queued for ${company.domain}.`
      setNotice(msg)
    } catch (err) { setError(parseError(err)) }
  }

  const onFetchContactsSelected = async () => {
    if (selectedCompanyIds.length === 0) return
    setError(''); setNotice(''); setIsFetchingContactsSelected(true)
    try {
      let queued = 0
      await Promise.all(selectedCompanyIds.map(async (id) => {
        try {
          const r = await fetchContactsForCompany(id)
          queued += r.queued_count
        } catch { /* skip individual failures */ }
      }))
      setNotice(`Queued contact fetch for ${queued} of ${selectedCompanyIds.length} selected companies.`)
    } catch (err) { setError(parseError(err)) }
    finally { setIsFetchingContactsSelected(false) }
  }

  const onFetchContactsForRun = async (run: RunRead) => {
    setError(''); setNotice('')
    try {
      const result = await fetchContactsForRun(run.id)
      setNotice(`Queued contact fetch for ${result.queued_count} Possible companies in run ${run.id.slice(0, 8)}….`)
    } catch (err) { setError(parseError(err)) }
  }

  // ── Derived ────────────────────────────────────────────────────────────
  const selectedPrompt = prompts.find((p) => p.id === selectedPromptId) ?? null
  const operationsEvents = buildOperationsEvents(operationsScrapeJobs, operationsRuns)
  const filteredOperationsEvents = operationsEvents.filter((event) => {
    if (operationsPipelineFilter !== 'all' && event.kind !== operationsPipelineFilter) return false
    if (operationsStatusFilter !== 'all' && event.status !== operationsStatusFilter) return false
    if (operationsErrorOnly && !event.error_code) return false
    if (operationsSearchQuery.trim()) {
      const needle = operationsSearchQuery.trim().toLowerCase()
      if (!event.search_blob.includes(needle)) return false
    }
    return true
  })
  const operationsActiveCount = operationsEvents.filter((event) => event.status === 'active').length
  const analyticsSnapshot: AnalyticsSnapshot = buildAnalyticsSnapshot(
    analyticsScrapeSample,
    analyticsRunSample,
    companyCounts,
  )
  const analyticsScrapeErrors: CountBucket[] = topScrapeErrorCodes(analyticsScrapeSample, 6)
  const analyticsFailedRunPrompts: CountBucket[] = topFailedRunPrompts(analyticsRunSample, 6)

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <>
      <AppShell
        activeView={activeView}
        setActiveView={setActiveView}
        stats={stats}
        selectedPrompt={selectedPrompt}
        onOpenPromptLibrary={openPromptSheet}
        exportUrl={getCompaniesExportUrl()}
      >
        {activeView === 'companies' && (
          <CompaniesView
            companies={companies}
            isLoading={isCompaniesLoading}
            companyOffset={companyOffset}
            pageSize={pageSize}
            decisionFilter={decisionFilter}
            scrapeFilter={scrapeFilter}
            selectedCompanyIds={selectedCompanyIds}
            companyCounts={companyCounts}
            actionState={actionState}
            analysisActionState={analysisActionState}
            isScrapingSelected={isScrapingSelected}
            isScrapingAll={isScrapingAll}
            isClassifyingSelected={isClassifyingSelected}
            isClassifyingAll={isClassifyingAll}
            isDeleting={isDeleting}
            isSelectingAll={isSelectingAll}
            isUploading={isUploading}
            isDragActive={isDragActive}
            file={file}
            selectedPrompt={selectedPrompt}
            utilitiesOpen={utilitiesOpen}
            letterFilter={letterFilter}
            letterCounts={letterCounts}
            onSetLetterFilter={(lf) => { setLetterFilter(lf); setCompanyOffset(0); companyCacheRef.current = {} }}
            onSetDecisionFilter={(f) => { setDecisionFilter(f); setCompanyOffset(0); companyCacheRef.current = {} }}
            onSetScrapeFilter={(f) => { setScrapeFilter(f); setCompanyOffset(0); companyCacheRef.current = {} }}
            onSetPageSize={(s) => { setPageSize(s); setCompanyOffset(0); companyCacheRef.current = {} }}
            onPagePrev={() => void loadCompanies(Math.max(companyOffset - (companies?.limit ?? pageSize), 0), pageSize, decisionFilter)}
            onPageNext={() => void loadCompanies(companyOffset + (companies?.limit ?? pageSize), pageSize, decisionFilter)}
            onToggleCompanySelection={toggleCompanySelection}
            onToggleVisibleSelection={toggleVisibleSelection}
            onSelectAllFiltered={() => void onSelectAllFiltered()}
            onClearSelection={() => setSelectedCompanyIds([])}
            onScrape={(c) => void onScrape(c)}
            onScrapeSelected={() => void onScrapeSelected()}
            onScrapeAll={() => void onScrapeAll()}
            onClassify={(c) => void onClassify(c)}
            onClassifySelected={() => void onClassifySelected()}
            onClassifyAll={() => void startClassification('all')}
            onDeleteSelected={() => void onDeleteSelected()}
            onSetFile={setFile}
            onSetIsDragActive={setIsDragActive}
            onUpload={onUpload}
            onToggleUtilities={() => setUtilitiesOpen((v) => !v)}
            onReviewCompany={(c) => void openCompanyReview(c)}
            onSetManualLabel={(c, label) => void setManualLabel(c, label)}
            onFetchContacts={(c) => onFetchContacts(c)}
            isFetchingContactsSelected={isFetchingContactsSelected}
            onFetchContactsSelected={() => void onFetchContactsSelected()}
          />
        )}

        {activeView === 'jobs' && (
          <ScrapeJobsView
            scrapeJobs={scrapeJobs}
            isLoading={isJobsLoading}
            jobsOffset={jobsOffset}
            jobsPageSize={jobsPageSize}
            jobsFilter={jobsFilter}
            jobsHasMore={jobsHasMore}
            onSetJobsFilter={(f) => { setJobsFilter(f); setJobsOffset(0) }}
            onSetJobsPageSize={setJobsPageSize}
            onPagePrev={() => void loadScrapeJobs(Math.max(jobsOffset - jobsPageSize, 0), jobsPageSize)}
            onPageNext={() => void loadScrapeJobs(jobsOffset + jobsPageSize, jobsPageSize)}
            onRefresh={() => void loadScrapeJobs(jobsOffset, jobsPageSize)}
            onViewMarkdown={(job) => void openMarkdownDrawer(job)}
          />
        )}

        {activeView === 'runs' && (
          <AnalysisRunsView
            runs={runs}
            isLoading={isRunsLoading}
            runsOffset={runsOffset}
            runsPageSize={runsPageSize}
            runsHasMore={runsHasMore}
            onSetRunsPageSize={setRunsPageSize}
            onPagePrev={() => void loadRuns(Math.max(runsOffset - runsPageSize, 0), runsPageSize)}
            onPageNext={() => void loadRuns(runsOffset + runsPageSize, runsPageSize)}
            onRefresh={() => void loadRuns(runsOffset, runsPageSize)}
            onInspectRun={(run) => void loadRunJobs(run)}
            onFetchContactsForRun={(run) => onFetchContactsForRun(run)}
          />
        )}

        {activeView === 'contacts' && (
          <ContactsView />
        )}

        {activeView === 'operations' && (
          <OperationsLogView
            events={filteredOperationsEvents}
            isLoading={isOperationsLoading}
            error={operationsError}
            pipelineFilter={operationsPipelineFilter}
            statusFilter={operationsStatusFilter}
            errorOnly={operationsErrorOnly}
            searchQuery={operationsSearchQuery}
            activeCount={operationsActiveCount}
            onSetPipelineFilter={setOperationsPipelineFilter}
            onSetStatusFilter={setOperationsStatusFilter}
            onSetErrorOnly={setOperationsErrorOnly}
            onSetSearchQuery={setOperationsSearchQuery}
            onRefresh={() => void loadOperationsSnapshot()}
            onInspectEvent={(event) => {
              if (event.scrape_job) {
                void openScrapeDiagnostics(event.scrape_job)
                return
              }
              if (event.run) void loadRunJobs(event.run)
            }}
          />
        )}

        {activeView === 'analytics' && (
          <AnalyticsSnapshotView
            stats={stats}
            companyCounts={companyCounts}
            snapshot={analyticsSnapshot}
            scrapeErrors={analyticsScrapeErrors}
            failedRunPrompts={analyticsFailedRunPrompts}
            isLoading={isAnalyticsLoading}
            error={analyticsError}
            onRefresh={() => void loadAnalyticsSnapshot()}
          />
        )}

        {/* Pipeline ops — visible in scrape jobs view toolbar area via stats */}
        {stats && activeView === 'jobs' && (
          <div className="mt-4 flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--oc-border)] bg-white p-3">
            <p className="mr-2 text-xs font-bold text-[var(--oc-muted)]">
              Pipeline ops ·{' '}
              <span className="font-normal text-[var(--oc-muted)]">
                as of {new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(new Date(stats.as_of))}
              </span>
            </p>
            <button
              type="button"
              onClick={() => void onResetStuck()}
              disabled={isResettingStuck || stats.scrape.stuck_count === 0}
              className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isResettingStuck ? 'Resetting…' : `Reset Stuck Scrape (${stats.scrape.stuck_count})`}
            </button>
            <button
              type="button"
              onClick={() => void onResetStuckAnalysis()}
              disabled={isResettingStuckAnalysis || (stats.analysis.running === 0 && stats.analysis.queued === 0)}
              className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isResettingStuckAnalysis ? 'Resetting…' : `Reset Stuck Analysis (${stats.analysis.running + stats.analysis.queued})`}
            </button>
            <button
              type="button"
              onClick={() => void onDrainQueue()}
              disabled={isDrainingQueue || (stats.scrape.queued === 0 && stats.analysis.queued === 0)}
              className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isDrainingQueue ? 'Draining…' : `Drain Queue (${stats.scrape.queued + stats.analysis.queued})`}
            </button>
          </div>
        )}
      </AppShell>

      {/* Panels (portaled above AppShell) */}
      <MarkdownPreviewPanel
        markdownJob={markdownJob}
        markdownPages={markdownPages}
        activeMarkdownPageKind={activeMarkdownPageKind}
        isMarkdownLoading={isMarkdownLoading}
        markdownError={markdownError}
        markdownCopyState={markdownCopyState}
        onClose={closeMarkdownDrawer}
        onSetActivePageKind={setActiveMarkdownPageKind}
        onCopyMarkdown={(content) => void copyMarkdown(content)}
      />

      <ScrapeDiagnosticsPanel
        job={diagnosticsJob}
        pages={diagnosticsPages}
        isLoading={isDiagnosticsLoading}
        error={diagnosticsError}
        onClose={closeScrapeDiagnostics}
        onOpenMarkdown={(job) => void openMarkdownDrawer(job)}
      />

      <PromptLibraryPanel
        isOpen={promptSheetOpen}
        onClose={closePromptSheet}
        prompts={prompts}
        selectedPromptId={selectedPromptId}
        editingPromptId={editingPromptId}
        promptName={promptName}
        promptText={promptText}
        promptEnabled={promptEnabled}
        isPromptsLoading={isPromptsLoading}
        isPromptSaving={isPromptSaving}
        promptError={promptError}
        onSelectPrompt={onSelectPrompt}
        onNewPrompt={onNewPrompt}
        onTogglePromptEnabled={(p) => void onTogglePromptEnabled(p)}
        onSaveAsNew={() => void onSavePromptAsNew()}
        onUpdateCurrent={() => void onUpdateCurrentPrompt()}
        onSetPromptName={setPromptName}
        onSetPromptText={setPromptText}
        onSetPromptEnabled={setPromptEnabled}
        onRefresh={() => void loadPrompts(selectedPromptId, editingPromptId !== null)}
      />

      <AnalysisDetailPanel
        inspectedRun={inspectedRun}
        runJobs={runJobs}
        isRunJobsLoading={isRunJobsLoading}
        runJobsError={runJobsError}
        analysisDetail={analysisDetail}
        isAnalysisDetailLoading={isAnalysisDetailLoading}
        analysisDetailError={analysisDetailError}
        onClose={closeRunDrawer}
        onInspectJob={(job) => void openAnalysisDetail(job)}
        onBackFromDetail={() => { setAnalysisDetail(null); setAnalysisDetailError('') }}
      />

      <CompanyReviewPanel
        company={reviewedCompany}
        detail={companyReviewDetail}
        isLoading={isCompanyReviewLoading}
        error={companyReviewError}
        isSaving={isFeedbackSaving}
        onClose={closeCompanyReview}
        onSave={(thumbs, comment) => void saveFeedback(thumbs, comment)}
      />

      <Toast error={error} notice={notice} />
    </>
  )
}

export default App
