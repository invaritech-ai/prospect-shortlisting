import { useCallback, useEffect, useRef, useState } from 'react'
import type { DragEvent, FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ApiError,
  createRuns,
  createPrompt,
  createScrapeJob,
  deleteCompanies,
  drainQueue,
  enqueueRunAll,
  getAnalysisJobDetail,
  getCompaniesExportUrl,
  getCompanyCounts,
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
} from './lib/api'
import type {
  AnalysisJobDetailRead,
  AnalysisRunJobRead,
  CompanyCounts,
  CompanyList,
  CompanyListItem,
  DecisionFilter,
  PipelineStageStats,
  PromptRead,
  RunRead,
  ScrapeFilter,
  ScrapeJobRead,
  ScrapePageContentRead,
  StatsResponse,
} from './lib/types'

const DEFAULT_COMPANY_PAGE_SIZE = 100
const PAGE_SIZE_OPTIONS = [50, 100, 200] as const
const DEFAULT_JOBS_PAGE_SIZE = 50
const JOBS_PAGE_SIZE_OPTIONS = [25, 50, 100] as const
const DEFAULT_RUNS_PAGE_SIZE = 25
const RUNS_PAGE_SIZE_OPTIONS = [25, 50, 100] as const
const PAGE_KIND_ORDER = ['home', 'about', 'products'] as const
const PAGE_KIND_LABELS: Record<(typeof PAGE_KIND_ORDER)[number], string> = {
  home: 'Home',
  about: 'About',
  products: 'Products',
}
const PROMPT_SELECTION_KEY = 'ps:selected-prompt-id'
type ActiveView = 'companies' | 'jobs' | 'runs'
type JobFilter = 'all' | 'active' | 'completed' | 'failed'
const JOB_FILTERS: Array<{ value: JobFilter; label: string }> = [
  { value: 'all', label: 'All jobs' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]
const DECISION_FILTERS: Array<{ value: DecisionFilter; label: string }> = [
  { value: 'all', label: 'All (ordered)' },
  { value: 'unlabeled', label: 'No label' },
  { value: 'possible', label: 'Possible' },
  { value: 'unknown', label: 'Unknown' },
  { value: 'crap', label: 'Crap' },
]
const SCRAPE_FILTERS: Array<{ value: ScrapeFilter; label: string }> = [
  { value: 'all', label: 'Any scrape' },
  { value: 'done', label: 'Scrape done' },
  { value: 'failed', label: 'Scrape failed' },
  { value: 'none', label: 'Not scraped' },
]

const MAX_POLL_FAILURES = 3

function App() {
  const companyCacheRef = useRef<Record<string, CompanyList>>({})
  const pollFailuresRef = useRef(0)
  const editingPromptIdRef = useRef<string | null>(null)
  const selectedPromptIdRef = useRef('')
  const [file, setFile] = useState<File | null>(null)
  const [companies, setCompanies] = useState<CompanyList | null>(null)
  const [companyOffset, setCompanyOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_COMPANY_PAGE_SIZE)
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>('all')
  const [scrapeFilter, setScrapeFilter] = useState<ScrapeFilter>('all')
  const [isCompaniesLoading, setIsCompaniesLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isScrapingSelected, setIsScrapingSelected] = useState(false)
  const [isScrapingAll, setIsScrapingAll] = useState(false)
  const [isClassifyingSelected, setIsClassifyingSelected] = useState(false)
  const [isClassifyingAll, setIsClassifyingAll] = useState(false)
  const [isDragActive, setIsDragActive] = useState(false)
  const [actionState, setActionState] = useState<Record<string, string>>({})
  const [analysisActionState, setAnalysisActionState] = useState<Record<string, string>>({})
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<string[]>([])
  const [scrapeJobs, setScrapeJobs] = useState<ScrapeJobRead[]>([])
  const [runs, setRuns] = useState<RunRead[]>([])
  const [activeView, setActiveView] = useState<ActiveView>('companies')
  const [utilitiesOpen, setUtilitiesOpen] = useState(false)
  const [promptSheetOpen, setPromptSheetOpen] = useState(false)
  const [prompts, setPrompts] = useState<PromptRead[]>([])
  const [selectedPromptId, setSelectedPromptIdState] = useState('')
  const setSelectedPromptId = (v: string) => { selectedPromptIdRef.current = v; setSelectedPromptIdState(v) }
  const [editingPromptId, setEditingPromptIdState] = useState<string | null>(null)
  const setEditingPromptId = (v: string | null) => { editingPromptIdRef.current = v; setEditingPromptIdState(v) }
  const [promptName, setPromptName] = useState('')
  const [promptText, setPromptText] = useState('')
  const [promptEnabled, setPromptEnabled] = useState(true)
  const [isPromptsLoading, setIsPromptsLoading] = useState(false)
  const [isPromptSaving, setIsPromptSaving] = useState(false)
  const [promptError, setPromptError] = useState('')
  const [jobsOffset, setJobsOffset] = useState(0)
  const [jobsPageSize, setJobsPageSize] = useState(DEFAULT_JOBS_PAGE_SIZE)
  const [jobsFilter, setJobsFilter] = useState<JobFilter>('all')
  const [isJobsLoading, setIsJobsLoading] = useState(false)
  const [jobsHasMore, setJobsHasMore] = useState(false)
  const [runsOffset, setRunsOffset] = useState(0)
  const [runsPageSize, setRunsPageSize] = useState(DEFAULT_RUNS_PAGE_SIZE)
  const [isRunsLoading, setIsRunsLoading] = useState(false)
  const [runsHasMore, setRunsHasMore] = useState(false)
  const [inspectedRun, setInspectedRun] = useState<RunRead | null>(null)
  const [runJobs, setRunJobs] = useState<AnalysisRunJobRead[]>([])
  const [isRunJobsLoading, setIsRunJobsLoading] = useState(false)
  const [runJobsError, setRunJobsError] = useState('')
  const [analysisDetail, setAnalysisDetail] = useState<AnalysisJobDetailRead | null>(null)
  const [isAnalysisDetailLoading, setIsAnalysisDetailLoading] = useState(false)
  const [analysisDetailError, setAnalysisDetailError] = useState('')
  const [markdownJob, setMarkdownJob] = useState<ScrapeJobRead | null>(null)
  const [markdownPages, setMarkdownPages] = useState<ScrapePageContentRead[]>([])
  const [activeMarkdownPageKind, setActiveMarkdownPageKind] = useState<string>('')
  const [isMarkdownLoading, setIsMarkdownLoading] = useState(false)
  const [markdownError, setMarkdownError] = useState('')
  const [markdownCopyState, setMarkdownCopyState] = useState('')
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [companyCounts, setCompanyCounts] = useState<CompanyCounts | null>(null)
  const [isDrainingQueue, setIsDrainingQueue] = useState(false)
  const [isResettingStuck, setIsResettingStuck] = useState(false)
  const [isResettingStuckAnalysis, setIsResettingStuckAnalysis] = useState(false)
  const [isSelectingAll, setIsSelectingAll] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const parseError = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (typeof err.detail === 'string') {
        return err.detail
      }
      if (
        typeof err.detail === 'object' &&
        err.detail !== null &&
        'message' in err.detail &&
        typeof (err.detail as { message: unknown }).message === 'string'
      ) {
        return (err.detail as { message: string }).message
      }
      if (Array.isArray(err.detail)) {
        return JSON.stringify(err.detail)
      }
      return JSON.stringify(err.detail)
    }
    if (err instanceof Error) {
      return err.message
    }
    return 'Unknown error'
  }

  const cacheKeyFor = useCallback(
    (offset: number, limit: number, nextDecisionFilter: DecisionFilter, nextScrapeFilter: ScrapeFilter): string =>
      `${nextDecisionFilter}:${nextScrapeFilter}:${limit}:${offset}`,
    [],
  )

  const prefetchCompanies = useCallback(
    async (offset: number, limit: number, nextDecisionFilter: DecisionFilter, nextScrapeFilter: ScrapeFilter) => {
      const key = cacheKeyFor(offset, limit, nextDecisionFilter, nextScrapeFilter)
      if (companyCacheRef.current[key]) {
        return
      }
      try {
        const response = await listCompanies(limit, offset, nextDecisionFilter, false, nextScrapeFilter)
        companyCacheRef.current[key] = response
      } catch {
        // Prefetch should never interrupt operator flow.
      }
    },
    [cacheKeyFor],
  )

  const loadCompanies = useCallback(
    async (
      offset = 0,
      nextLimit = pageSize,
      nextDecisionFilter: DecisionFilter = decisionFilter,
      nextScrapeFilter: ScrapeFilter = scrapeFilter,
      forceRefresh = false,
    ) => {
      const key = cacheKeyFor(offset, nextLimit, nextDecisionFilter, nextScrapeFilter)
      const cached = companyCacheRef.current[key]
      if (cached && !forceRefresh) {
        setCompanies(cached)
        setCompanyOffset(offset)
        void prefetchCompanies(offset + nextLimit, nextLimit, nextDecisionFilter, nextScrapeFilter)
        return
      }

      setIsCompaniesLoading(true)
      try {
        const response = await listCompanies(nextLimit, offset, nextDecisionFilter, false, nextScrapeFilter)
        companyCacheRef.current[key] = response
        setCompanies(response)
        setCompanyOffset(offset)
        pollFailuresRef.current = 0
        if (response.has_more) {
          void prefetchCompanies(offset + nextLimit, nextLimit, nextDecisionFilter, nextScrapeFilter)
        }
      } catch (err) {
        setError(parseError(err))
      } finally {
        setIsCompaniesLoading(false)
      }
    },
    [cacheKeyFor, decisionFilter, scrapeFilter, pageSize, prefetchCompanies],
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

        const storedPromptId = window.localStorage.getItem(PROMPT_SELECTION_KEY) ?? ''
        const preferredEnabledId =
          (preferredPromptId && rows.find((item) => item.id === preferredPromptId && item.enabled)?.id) ||
          (selectedPromptIdRef.current && rows.find((item) => item.id === selectedPromptIdRef.current && item.enabled)?.id) ||
          rows.find((item) => item.id === storedPromptId && item.enabled)?.id ||
          rows.find((item) => item.enabled)?.id ||
          rows[0]?.id ||
          ''

        setSelectedPromptId(preferredEnabledId)
        if (preferredEnabledId) {
          window.localStorage.setItem(PROMPT_SELECTION_KEY, preferredEnabledId)
        } else {
          window.localStorage.removeItem(PROMPT_SELECTION_KEY)
        }

        if (!preserveEditor) {
          const promptForEditor =
            rows.find((item) => item.id === (preferredPromptId || editingPromptIdRef.current || preferredEnabledId)) ?? rows[0] ?? null
          if (promptForEditor) {
            setEditingPromptId(promptForEditor.id)
            setPromptName(promptForEditor.name)
            setPromptText(promptForEditor.prompt_text)
            setPromptEnabled(promptForEditor.enabled)
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
    [], // stable — reads editingPromptIdRef/selectedPromptIdRef via refs, never re-created
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
    } catch {
      // non-critical — counts will just be absent
    }
  }, [])

  useEffect(() => {
    setSelectedCompanyIds([])
    setCompanyOffset(0)
    companyCacheRef.current = {}
    void loadCompanies(0, pageSize, decisionFilter, scrapeFilter)
  }, [decisionFilter, scrapeFilter, loadCompanies, pageSize])

  useEffect(() => {
    void loadScrapeJobs(0, jobsPageSize)
  }, [jobsFilter, jobsPageSize, loadScrapeJobs])

  useEffect(() => {
    void loadRuns(0, runsPageSize)
  }, [runsPageSize, loadRuns])

  useEffect(() => {
    void loadPrompts()
  }, [loadPrompts])

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
    const timer = window.setTimeout(() => setError(''), 5000)
    return () => window.clearTimeout(timer)
  }, [error])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    const hasActiveJobs = scrapeJobs.some((job) => !job.terminal_state)
    if (!hasActiveJobs) {
      return
    }
    const timer = window.setInterval(() => {
      void loadScrapeJobs(jobsOffset, jobsPageSize)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [jobsOffset, jobsPageSize, loadScrapeJobs, scrapeJobs])

  useEffect(() => {
    const hasActiveRuns = runs.some((run) => run.status === 'running' || run.status === 'created')
    if (!hasActiveRuns) {
      return
    }
    const timer = window.setInterval(() => {
      if (pollFailuresRef.current >= MAX_POLL_FAILURES) return
      void loadRuns(runsOffset, runsPageSize)
      void loadCompanies(companyOffset, pageSize, decisionFilter, scrapeFilter, true)
    }, 4000)
    return () => window.clearInterval(timer)
  }, [companyOffset, decisionFilter, scrapeFilter, loadCompanies, loadRuns, pageSize, runs, runsOffset, runsPageSize])

  useEffect(() => {
    if (!markdownJob) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMarkdownJob(null)
        setMarkdownPages([])
        setActiveMarkdownPageKind('')
        setMarkdownError('')
        setMarkdownCopyState('')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [markdownJob])

  useEffect(() => {
    if (!selectedPromptId) {
      return
    }
    window.localStorage.setItem(PROMPT_SELECTION_KEY, selectedPromptId)
  }, [selectedPromptId])

  const onUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!file) {
      setError('Choose a file first.')
      return
    }
    setError('')
    setNotice('')
    setIsUploading(true)
    try {
      await uploadFile(file)
      companyCacheRef.current = {}
      setFile(null)
      setSelectedCompanyIds([])
      await loadCompanies(0, pageSize, decisionFilter)
      void loadCompanyCounts()
      setNotice('Upload parsed and companies refreshed.')
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsUploading(false)
    }
  }

  const onDragOver = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setIsDragActive(true)
  }

  const onDragLeave = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setIsDragActive(false)
  }

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setIsDragActive(false)
    const droppedFile = event.dataTransfer.files?.[0]
    if (!droppedFile) {
      return
    }
    setFile(droppedFile)
    setError('')
  }

  const onScrape = async (company: CompanyListItem) => {
    if (company.latest_scrape_terminal === false) {
      setNotice(`Scrape already active for ${company.domain}.`)
      return
    }
    setError('')
    setNotice('')
    setActionState((current) => ({ ...current, [company.id]: 'Creating scrape job...' }))
    try {
      const job = await createScrapeJob({ website_url: company.normalized_url })
      await enqueueRunAll(job.id)
      companyCacheRef.current = {}
      await loadCompanies(companyOffset, pageSize, decisionFilter)
      await loadScrapeJobs(0, jobsPageSize)
      setActionState((current) => ({ ...current, [company.id]: 'Queued' }))
    } catch (err) {
      setActionState((current) => ({ ...current, [company.id]: 'Failed' }))
      setError(parseError(err))
    }
  }

  const toggleCompanySelection = (companyId: string) => {
    setSelectedCompanyIds((current) =>
      current.includes(companyId) ? current.filter((item) => item !== companyId) : [...current, companyId],
    )
  }

  const toggleVisibleSelection = () => {
    if (!companies) {
      return
    }
    const visibleIds = companies.items.map((item) => item.id)
    const allVisibleSelected = visibleIds.every((id) => selectedCompanyIds.includes(id))
    setSelectedCompanyIds((current) => {
      if (allVisibleSelected) {
        return current.filter((id) => !visibleIds.includes(id))
      }
      return Array.from(new Set([...current, ...visibleIds]))
    })
  }

  const onSelectAllFiltered = async () => {
    setIsSelectingAll(true)
    try {
      const result = await listCompanyIds(decisionFilter, scrapeFilter)
      setSelectedCompanyIds(result.ids)
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsSelectingAll(false)
    }
  }

  const onDeleteSelected = async () => {
    if (selectedCompanyIds.length === 0) {
      return
    }
    const confirmed = window.confirm(
      `Permanently delete ${selectedCompanyIds.length} compan${selectedCompanyIds.length === 1 ? 'y' : 'ies'}? This cannot be undone.`,
    )
    if (!confirmed) {
      return
    }

    setError('')
    setNotice('')
    setIsDeleting(true)
    try {
      await deleteCompanies(selectedCompanyIds)
      companyCacheRef.current = {}
      const currentLimit = companies?.limit ?? pageSize
      const nextOffset =
        companies && companies.items.length === selectedCompanyIds.length && companyOffset > 0
          ? Math.max(companyOffset - currentLimit, 0)
          : companyOffset
      await loadCompanies(nextOffset, pageSize, decisionFilter)
      void loadCompanyCounts()
      setNotice(`Deleted ${selectedCompanyIds.length} companies.`)
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsDeleting(false)
    }
  }

  const onScrapeSelected = async () => {
    if (selectedCompanyIds.length === 0) {
      return
    }
    setError('')
    setNotice('')
    setIsScrapingSelected(true)
    try {
      const result = await scrapeSelectedCompanies(selectedCompanyIds)
      companyCacheRef.current = {}
      await loadCompanies(companyOffset, pageSize, decisionFilter)
      await loadScrapeJobs(0, jobsPageSize)
      const message = `Queued ${result.queued_count}/${result.requested_count} selected companies for scraping.`
      if (result.failed_company_ids.length > 0) {
        setError(`${message} ${result.failed_company_ids.length} failed to enqueue.`)
      } else {
        setNotice(message)
      }
      setActionState((current) => {
        const next = { ...current }
        const failedSet = new Set(result.failed_company_ids)
        for (const companyId of selectedCompanyIds) {
          next[companyId] = failedSet.has(companyId) ? 'Skipped' : 'Queued'
        }
        return next
      })
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsScrapingSelected(false)
    }
  }

  const onScrapeAll = async () => {
    setError('')
    setNotice('')
    setIsScrapingAll(true)
    try {
      const result = await scrapeAllCompanies()
      companyCacheRef.current = {}
      await loadCompanies(0, pageSize, decisionFilter)
      await loadScrapeJobs(0, jobsPageSize)
      void loadCompanyCounts()
      setSelectedCompanyIds([])
      const message = `Queued ${result.queued_count}/${result.requested_count} companies for scraping.`
      if (result.failed_company_ids.length > 0) {
        setError(`${message} ${result.failed_company_ids.length} failed to enqueue.`)
      } else {
        setNotice(message)
      }
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsScrapingAll(false)
    }
  }

  const startClassification = async (scope: 'all' | 'selected', companyIds: string[] = []) => {
    if (!selectedPrompt || !selectedPrompt.enabled) {
      setError('Select an enabled prompt before starting classification.')
      return
    }

    setError('')
    setNotice('')
    if (scope === 'all') {
      setIsClassifyingAll(true)
    } else {
      setIsClassifyingSelected(true)
    }

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
      const message = `Created ${runCount} run${runCount === 1 ? '' : 's'} and queued ${result.queued_count}/${result.requested_count} classifications.`
      if (result.skipped_company_ids.length > 0) {
        setNotice(`${message} Skipped ${result.skipped_company_ids.length} companies without completed scrape markdown.`)
      } else {
        setNotice(message)
      }
      if (scope === 'selected') {
        setAnalysisActionState((current) => {
          const next = { ...current }
          const skipped = new Set(result.skipped_company_ids)
          for (const companyId of companyIds) {
            next[companyId] = skipped.has(companyId) ? 'Skipped' : 'Queued'
          }
          return next
        })
      }
    } catch (err) {
      setError(parseError(err))
    } finally {
      if (scope === 'all') {
        setIsClassifyingAll(false)
      } else {
        setIsClassifyingSelected(false)
      }
    }
  }

  const onClassify = async (company: CompanyListItem) => {
    setAnalysisActionState((current) => ({ ...current, [company.id]: 'Queuing…' }))
    await startClassification('selected', [company.id])
  }

  const onClassifySelected = async () => {
    if (selectedCompanyIds.length === 0) {
      return
    }
    setAnalysisActionState((current) => {
      const next = { ...current }
      for (const id of selectedCompanyIds) next[id] = 'Queuing…'
      return next
    })
    await startClassification('selected', selectedCompanyIds)
  }

  const onClassifyAll = async () => {
    await startClassification('all')
  }

  const closeMarkdownDrawer = () => {
    setMarkdownJob(null)
    setMarkdownPages([])
    setActiveMarkdownPageKind('')
    setMarkdownError('')
    setMarkdownCopyState('')
  }

  const closeRunDrawer = () => {
    setInspectedRun(null)
    setRunJobs([])
    setAnalysisDetail(null)
    setRunJobsError('')
    setAnalysisDetailError('')
  }

  const openAnalysisDetail = async (job: AnalysisRunJobRead) => {
    setAnalysisDetail(null)
    setAnalysisDetailError('')
    setIsAnalysisDetailLoading(true)
    try {
      const detail = await getAnalysisJobDetail(job.analysis_job_id)
      setAnalysisDetail(detail)
    } catch (err) {
      setAnalysisDetailError(parseError(err))
    } finally {
      setIsAnalysisDetailLoading(false)
    }
  }

  const openMarkdownDrawer = async (job: ScrapeJobRead) => {
    setMarkdownJob(job)
    setMarkdownPages([])
    setActiveMarkdownPageKind('')
    setMarkdownError('')
    setMarkdownCopyState('')
    setIsMarkdownLoading(true)
    try {
      const pages = await listScrapeJobPageContents(job.id)
      const filtered = PAGE_KIND_ORDER.map((kind) =>
        pages.find((page) => page.page_kind === kind && page.markdown_content.trim().length > 0),
      ).filter((page): page is ScrapePageContentRead => !!page)
      setMarkdownPages(filtered)
      setActiveMarkdownPageKind(filtered[0]?.page_kind ?? '')
      if (filtered.length === 0) {
        setMarkdownError('No markdown available for this scrape job.')
      }
    } catch (err) {
      setMarkdownError(parseError(err))
    } finally {
      setIsMarkdownLoading(false)
    }
  }

  const copyMarkdown = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setMarkdownCopyState('Copied')
      window.setTimeout(() => setMarkdownCopyState(''), 1600)
    } catch {
      setMarkdownCopyState('Copy failed')
      window.setTimeout(() => setMarkdownCopyState(''), 1600)
    }
  }

  const openPromptSheet = () => {
    setPromptSheetOpen(true)
    if (prompts.length === 0) {
      void loadPrompts()
    }
  }

  const closePromptSheet = () => {
    setPromptSheetOpen(false)
    setPromptError('')
  }

  const loadPromptIntoEditor = (prompt: PromptRead) => {
    setEditingPromptId(prompt.id)
    setPromptName(prompt.name)
    setPromptText(prompt.prompt_text)
    setPromptEnabled(prompt.enabled)
  }

  const onSelectPrompt = (prompt: PromptRead) => {
    setSelectedPromptId(prompt.id)
    loadPromptIntoEditor(prompt)
  }

  const onNewPrompt = () => {
    setEditingPromptId(null)
    setPromptName('')
    setPromptText('')
    setPromptEnabled(true)
    setPromptError('')
  }

  const onSavePromptAsNew = async () => {
    if (!promptName.trim() || !promptText.trim()) {
      setPromptError('Name and prompt text are required.')
      return
    }
    setIsPromptSaving(true)
    try {
      const created = await createPrompt({
        name: promptName.trim(),
        prompt_text: promptText.trim(),
        enabled: promptEnabled,
      })
      await loadPrompts(created.id)
      setNotice(`Prompt "${created.name}" created.`)
      setError('')
    } catch (err) {
      setPromptError(parseError(err))
    } finally {
      setIsPromptSaving(false)
    }
  }

  const onUpdateCurrentPrompt = async () => {
    if (!editingPromptId) {
      setPromptError('Select an existing prompt to update.')
      return
    }
    if (!promptName.trim() || !promptText.trim()) {
      setPromptError('Name and prompt text are required.')
      return
    }
    setIsPromptSaving(true)
    try {
      const updated = await updatePrompt(editingPromptId, {
        name: promptName.trim(),
        prompt_text: promptText.trim(),
        enabled: promptEnabled,
      })
      await loadPrompts(updated.id)
      setNotice(`Prompt "${updated.name}" updated.`)
      setError('')
    } catch (err) {
      setPromptError(parseError(err))
    } finally {
      setIsPromptSaving(false)
    }
  }

  const onTogglePromptEnabled = async (prompt: PromptRead) => {
    setIsPromptSaving(true)
    try {
      const updated = await updatePrompt(prompt.id, { enabled: !prompt.enabled })
      await loadPrompts(updated.id, editingPromptId !== updated.id)
      if (editingPromptId === updated.id) {
        setPromptEnabled(updated.enabled)
      }
    } catch (err) {
      setPromptError(parseError(err))
    } finally {
      setIsPromptSaving(false)
    }
  }

  const onDrainQueue = async () => {
    const confirmed = window.confirm(
      'Cancel all queued jobs? This removes them from Redis and marks them as cancelled in the database.',
    )
    if (!confirmed) return
    setError('')
    setNotice('')
    setIsDrainingQueue(true)
    try {
      const result = await drainQueue()
      await Promise.all([loadScrapeJobs(0, jobsPageSize), loadStats()])
      setNotice(
        `Drained ${result.drained.toLocaleString()} tasks from queue and cancelled ${result.cancelled_db_jobs.toLocaleString()} jobs.`,
      )
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsDrainingQueue(false)
    }
  }

  const onResetStuck = async () => {
    setError('')
    setNotice('')
    setIsResettingStuck(true)
    try {
      const result = await resetStuckJobs()
      await Promise.all([loadScrapeJobs(0, jobsPageSize), loadStats()])
      setNotice(`Reset and re-queued ${result.reset_count.toLocaleString()} stuck scrape jobs.`)
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsResettingStuck(false)
    }
  }

  const onResetStuckAnalysis = async () => {
    setError('')
    setNotice('')
    setIsResettingStuckAnalysis(true)
    try {
      const result = await resetStuckAnalysisJobs()
      await Promise.all([
        loadCompanies(companyOffset, pageSize, decisionFilter, scrapeFilter, true),
        loadRuns(0, runsPageSize),
        loadStats(),
      ])
      setNotice(`Reset and re-queued ${result.reset_count.toLocaleString()} stuck analysis jobs.`)
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsResettingStuckAnalysis(false)
    }
  }

  const renderStageStats = (label: string, stage: PipelineStageStats) => (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-sm font-bold text-[var(--oc-text)]">{label}</span>
        <span className="font-mono text-xs text-[var(--oc-muted)]" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {stage.pct_done}%
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[var(--oc-border)]">
        <div
          className="h-full rounded-full bg-[var(--oc-accent)] transition-[width] duration-500"
          style={{ width: `${Math.min(stage.pct_done, 100)}%` }}
          role="progressbar"
          aria-valuenow={stage.pct_done}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label} progress`}
        />
      </div>
      <div
        className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        <span className="text-[var(--oc-muted)]">{stage.completed.toLocaleString()} done</span>
        {stage.running > 0 && (
          <span className="text-[var(--oc-info-text)]">{stage.running.toLocaleString()} running</span>
        )}
        {stage.queued > 0 && (
          <span className="text-[var(--oc-muted)]">{stage.queued.toLocaleString()} queued</span>
        )}
        {stage.failed > 0 && (
          <span className="text-[var(--oc-fail-text)]">{stage.failed.toLocaleString()} failed</span>
        )}
        {stage.avg_job_sec != null && (
          <span className="text-[var(--oc-muted)]">avg {stage.avg_job_sec}s/job</span>
        )}
        {stage.eta_at && (
          <span className="font-semibold text-[var(--oc-accent-ink)]">
            ETA {new Intl.DateTimeFormat(undefined, { timeStyle: 'short' }).format(new Date(stage.eta_at))}
          </span>
        )}
      </div>
    </div>
  )

  const effectiveTotal: number | null =
    (companies?.total ?? null) !== null ? companies!.total : companyCounts?.total ?? null
  const rangeLabel =
    companies && effectiveTotal !== null && effectiveTotal > 0
      ? `${Math.min(companies.offset + 1, effectiveTotal)}-${Math.min(companies.offset + companies.items.length, effectiveTotal)} of ${effectiveTotal.toLocaleString()}`
      : companies && companies.items.length > 0
        ? `${companies.offset + 1}-${companies.offset + companies.items.length}`
      : '0 of 0'
  const allVisibleSelected =
    companies ? companies.items.length > 0 && companies.items.every((item) => selectedCompanyIds.includes(item.id)) : false
  const canPagePrev = !!companies && companyOffset > 0 && !isCompaniesLoading
  const canPageNext = !!companies && companies.has_more && !isCompaniesLoading

  const decisionBadgeClass = (decision: string | null): string => {
    if (!decision) {
      return 'bg-slate-100 text-slate-600'
    }
    const token = decision.trim().toLowerCase()
    if (token === 'possible') {
      return 'bg-emerald-50 text-emerald-800'
    }
    if (token === 'unknown') {
      return 'bg-amber-50 text-amber-800'
    }
    if (token === 'crap') {
      return 'bg-rose-50 text-rose-800'
    }
    return 'bg-indigo-50 text-indigo-800'
  }

  const scrapeBadgeForCompany = (item: CompanyListItem): { label: string; className: string; title: string } => {
    const status = item.latest_scrape_status ?? 'not_started'
    const stage1 = item.latest_scrape_stage1_status ?? '-'
    const stage2 = item.latest_scrape_stage2_status ?? '-'
    const title = `status: ${status} | stage1: ${stage1} | stage2: ${stage2}`
    if (!item.latest_scrape_status) {
      return { label: 'Not started', className: 'oc-badge oc-badge-neutral', title }
    }
    if (item.latest_scrape_terminal === false) {
      if (stage1 === 'running') {
        return { label: 'Stage 1', className: 'oc-badge oc-badge-info', title }
      }
      if (stage2 === 'running') {
        return { label: 'Stage 2', className: 'oc-badge oc-badge-info', title }
      }
      return { label: 'Running', className: 'oc-badge oc-badge-info', title }
    }
    if (status.includes('failed') || stage1 === 'failed' || stage2 === 'failed') {
      return { label: 'Failed', className: 'oc-badge oc-badge-fail', title }
    }
    if (status === 'completed' || stage2 === 'completed') {
      return { label: 'Done', className: 'oc-badge oc-badge-success', title }
    }
    return { label: 'Queued', className: 'oc-badge oc-badge-neutral', title }
  }

  const badgeForJob = (job: ScrapeJobRead): { className: string; label: string } => {
    if (!job.terminal_state) {
      return {
        className: 'oc-badge oc-badge-info',
        label: job.stage2_status === 'running' ? 'Stage 2' : job.stage1_status === 'running' ? 'Stage 1' : job.status,
      }
    }
    if (isFailedJob(job)) {
      return { className: 'oc-badge oc-badge-fail', label: 'Failed' }
    }
    return { className: 'oc-badge oc-badge-success', label: 'Done' }
  }

  const isFailedJob = (job: ScrapeJobRead): boolean =>
    job.status.includes('failed') ||
    job.stage1_status === 'failed' ||
    job.stage2_status === 'failed' ||
    !!job.last_error_code

  const jobsRangeLabel =
    scrapeJobs.length > 0
      ? `${jobsOffset + 1}-${jobsOffset + scrapeJobs.length}`
      : '0 of 0'
  const runsRangeLabel =
    runs.length > 0
      ? `${runsOffset + 1}-${runsOffset + runs.length}`
      : '0 of 0'
  const activeMarkdownPage =
    markdownPages.find((page) => page.page_kind === activeMarkdownPageKind) ?? null
  const selectedPrompt = prompts.find((item) => item.id === selectedPromptId) ?? null

  const runBadge = (run: RunRead): { className: string; label: string } => {
    if (run.status === 'running' || run.status === 'created') {
      return { className: 'oc-badge oc-badge-info', label: 'Running' }
    }
    if (run.status === 'failed') {
      return { className: 'oc-badge oc-badge-fail', label: 'Failed' }
    }
    return { className: 'oc-badge oc-badge-success', label: 'Done' }
  }

  const analysisStateBadge = (state: string, terminalState: boolean): { className: string; label: string } => {
    const normalized = state.toLowerCase()
    if (!terminalState && (normalized === 'running' || normalized === 'queued')) {
      return { className: 'oc-badge oc-badge-info', label: normalized === 'queued' ? 'Queued' : 'Running' }
    }
    if (normalized === 'failed' || normalized === 'dead') {
      return { className: 'oc-badge oc-badge-fail', label: 'Failed' }
    }
    if (normalized === 'succeeded') {
      return { className: 'oc-badge oc-badge-success', label: 'Done' }
    }
    return { className: 'oc-badge oc-badge-neutral', label: state }
  }

  const decisionBadgeForLabel = (label: string | null): string => {
    if (!label) {
      return 'oc-badge oc-badge-neutral'
    }
    const normalized = label.toLowerCase()
    if (normalized === 'possible') {
      return 'oc-badge oc-badge-success'
    }
    if (normalized === 'unknown') {
      return 'oc-badge oc-badge-neutral'
    }
    return 'oc-badge oc-badge-fail'
  }

  const evidencePayload = analysisDetail?.evidence_json ?? null
  const reasoningPayload = analysisDetail?.reasoning_json ?? null
  const evidenceItems =
    evidencePayload && Array.isArray(evidencePayload['evidence'])
      ? (evidencePayload['evidence'] as unknown[]).map((item) => String(item))
      : []
  const reasoningSignals =
    reasoningPayload && typeof reasoningPayload['signals'] === 'object' && reasoningPayload['signals']
      ? (reasoningPayload['signals'] as Record<string, unknown>)
      : {}
  const reasoningOtherFields =
    reasoningPayload && typeof reasoningPayload['other_fields'] === 'object' && reasoningPayload['other_fields']
      ? (reasoningPayload['other_fields'] as Record<string, unknown>)
      : {}
  const rawModelOutput =
    reasoningPayload && typeof reasoningPayload['raw_response'] === 'string'
      ? String(reasoningPayload['raw_response'])
      : ''

  const renderPager = () => (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() =>
          void loadCompanies(Math.max(companyOffset - (companies?.limit ?? pageSize), 0), pageSize, decisionFilter)
        }
        disabled={!canPagePrev}
        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        Prev
      </button>
      <button
        type="button"
        onClick={() => void loadCompanies(companyOffset + (companies?.limit ?? pageSize), pageSize, decisionFilter)}
        disabled={!canPageNext}
        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        Next
      </button>
      <span className="oc-kbd">{rangeLabel}</span>
    </div>
  )

  return (
    <div className="oc-shell">
      <main className="oc-main space-y-6">
        <header className="oc-panel p-5 md:p-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="oc-kbd mb-2">Prospect Pipeline</p>
              <h1 className="text-3xl font-extrabold tracking-tight text-[var(--oc-text)] md:text-4xl">
                Companies Queue
              </h1>
              <p className="mt-2 max-w-3xl text-sm text-[var(--oc-muted)] md:text-base">
                Start from the company list. Review uploaded domains, see decisions if they exist, and trigger scrape
                work directly from the operator table.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--oc-muted)]">API</p>
                  <p className="mt-1 font-semibold text-[var(--oc-accent-ink)]">{import.meta.env.VITE_API_BASE_URL}</p>
                </div>
                <a
                  href={getCompaniesExportUrl()}
                  className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-2 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                >
                  Export CSV
                </a>
              </div>
            </div>
            <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--oc-muted)]">Prompt</p>
                  <div className="mt-1 flex items-center gap-2">
                    <p className="truncate font-semibold text-[var(--oc-accent-ink)]">
                      {selectedPrompt ? selectedPrompt.name : 'No prompt selected'}
                    </p>
                    {selectedPrompt ? (
                      <span className={`oc-badge ${selectedPrompt.enabled ? 'oc-badge-success' : 'oc-badge-fail'}`}>
                        {selectedPrompt.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    ) : null}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={openPromptSheet}
                  className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-2 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                >
                  Open Library
                </button>
              </div>
            </div>
          </div>
        </header>

        {stats && (
          <section className="oc-panel p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="oc-kbd mb-1">Pipeline Status</p>
                <p className="text-xs text-[var(--oc-muted)]">
                  as of {new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(new Date(stats.as_of))}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => void onResetStuck()}
                  disabled={isResettingStuck || stats.scrape.running === 0}
                  className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isResettingStuck ? 'Resetting…' : `Reset Stuck Scrape (${stats.scrape.running.toLocaleString()})`}
                </button>
                <button
                  type="button"
                  onClick={() => void onResetStuckAnalysis()}
                  disabled={isResettingStuckAnalysis || stats.analysis.running === 0}
                  className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isResettingStuckAnalysis ? 'Resetting…' : `Reset Stuck Analysis (${stats.analysis.running.toLocaleString()})`}
                </button>
                <button
                  type="button"
                  onClick={() => void onDrainQueue()}
                  disabled={isDrainingQueue || (stats.scrape.queued === 0 && stats.analysis.queued === 0)}
                  className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isDrainingQueue ? 'Draining…' : `Drain Queue (${(stats.scrape.queued + stats.analysis.queued).toLocaleString()})`}
                </button>
              </div>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              {renderStageStats('Scrape', stats.scrape)}
              {renderStageStats('Analysis', stats.analysis)}
            </div>
          </section>
        )}

        <section>
          <div className="oc-folder-rail">
            <button type="button" className="oc-folder-tab" data-active={activeView === 'companies'} onClick={() => setActiveView('companies')}>
              <span className="oc-folder-title">Companies</span>
              <span className="oc-folder-meta">{rangeLabel}</span>
            </button>
            <button type="button" className="oc-folder-tab" data-active={activeView === 'jobs'} onClick={() => setActiveView('jobs')}>
              <span className="oc-folder-title">Scrape Jobs</span>
              <span className="oc-folder-meta">{jobsRangeLabel}</span>
            </button>
            <button type="button" className="oc-folder-tab" data-active={activeView === 'runs'} onClick={() => setActiveView('runs')}>
              <span className="oc-folder-title">Analysis Runs</span>
              <span className="oc-folder-meta">{runsRangeLabel}</span>
            </button>
          </div>

          <section className="oc-panel rounded-tl-none p-5 md:p-6">
            {activeView === 'companies' ? (
              <>
                <div className="oc-toolbar">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-bold tracking-tight">All Companies</h2>
                      <p className="mt-1 text-sm text-[var(--oc-muted)]">
                        Dense operator view. Side scroll is acceptable; row height is kept strict.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setUtilitiesOpen((current) => !current)}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                      >
                        {utilitiesOpen ? 'Hide ingest' : 'Show ingest'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void onScrapeAll()}
                        disabled={isScrapingAll || isCompaniesLoading}
                        className="rounded-lg border border-[var(--oc-accent)] bg-[var(--oc-accent)] px-3 py-1.5 text-xs font-bold text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isScrapingAll ? 'Scraping all...' : 'Scrape all'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void onClassifyAll()}
                        disabled={!selectedPrompt || !selectedPrompt.enabled || isClassifyingAll}
                        className="rounded-lg border border-[var(--oc-accent)] bg-[var(--oc-accent-soft)] px-3 py-1.5 text-xs font-bold text-[var(--oc-accent-ink)] transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isClassifyingAll ? 'Classifying all...' : 'Classify all'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void onSelectAllFiltered()}
                        disabled={isSelectingAll}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-slate-500 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isSelectingAll ? 'Selecting…' : 'Select all matching'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void onScrapeSelected()}
                        disabled={selectedCompanyIds.length === 0 || isScrapingSelected}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isScrapingSelected ? 'Scraping selected...' : `Scrape selected (${selectedCompanyIds.length})`}
                      </button>
                      <button
                        type="button"
                        onClick={() => void onClassifySelected()}
                        disabled={selectedCompanyIds.length === 0 || !selectedPrompt || !selectedPrompt.enabled || isClassifyingSelected}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isClassifyingSelected ? 'Classifying selected...' : `Classify selected (${selectedCompanyIds.length})`}
                      </button>
                      <button
                        type="button"
                        onClick={() => void onDeleteSelected()}
                        disabled={selectedCompanyIds.length === 0 || isDeleting}
                        className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isDeleting ? 'Deleting...' : `Delete selected (${selectedCompanyIds.length})`}
                      </button>
                      <label className="text-xs font-semibold text-[var(--oc-muted)]">
                        Rows
                        <select
                          value={pageSize}
                          onChange={(event) => setPageSize(Number(event.target.value))}
                          className="ml-2 rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1 text-xs font-semibold text-[var(--oc-text)]"
                        >
                          {PAGE_SIZE_OPTIONS.map((size) => (
                            <option key={size} value={size}>
                              {size}
                            </option>
                          ))}
                        </select>
                      </label>
                      {renderPager()}
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {DECISION_FILTERS.map((item) => {
                      const countMap: Record<string, number | undefined> = {
                        all: companyCounts?.total,
                        unlabeled: companyCounts?.unlabeled,
                        possible: companyCounts?.possible,
                        unknown: companyCounts?.unknown,
                        crap: companyCounts?.crap,
                      }
                      const count = countMap[item.value]
                      return (
                        <button
                          key={item.value}
                          type="button"
                          onClick={() => setDecisionFilter(item.value)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                            decisionFilter === item.value
                              ? 'bg-[var(--oc-accent)] text-white'
                              : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                          }`}
                        >
                          {item.label}
                          {count !== undefined && (
                            <span className={`ml-1.5 rounded px-1 py-0.5 text-[10px] font-semibold ${decisionFilter === item.value ? 'bg-white/20' : 'bg-slate-100 text-slate-500'}`}>
                              {count.toLocaleString()}
                            </span>
                          )}
                        </button>
                      )
                    })}
                    <span className="text-[var(--oc-border)]">|</span>
                    {SCRAPE_FILTERS.map((item) => {
                      const countMap: Record<string, number | undefined> = {
                        all: companyCounts?.total,
                        done: companyCounts?.scrape_done,
                        failed: companyCounts?.scrape_failed,
                        none: companyCounts?.not_scraped,
                      }
                      const count = countMap[item.value]
                      return (
                        <button
                          key={item.value}
                          type="button"
                          onClick={() => setScrapeFilter(item.value)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                            scrapeFilter === item.value
                              ? 'bg-slate-700 text-white'
                              : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                          }`}
                        >
                          {item.label}
                          {count !== undefined && (
                            <span className={`ml-1.5 rounded px-1 py-0.5 text-[10px] font-semibold ${scrapeFilter === item.value ? 'bg-white/20' : 'bg-slate-100 text-slate-500'}`}>
                              {count.toLocaleString()}
                            </span>
                          )}
                        </button>
                      )
                    })}
                  </div>

                  {utilitiesOpen && (
                    <form onSubmit={onUpload} className="mt-3 rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-bold tracking-tight">Ingest File</h3>
                          <p className="mt-1 text-xs text-[var(--oc-muted)]">Upload is secondary and collapsible so the operator table stays dominant.</p>
                        </div>
                        <span className="oc-kbd">utility</span>
                      </div>
                      <div className="mt-3 grid gap-3 lg:grid-cols-[1fr_auto]">
                        <label
                          htmlFor="upload-file"
                          onDragOver={onDragOver}
                          onDragLeave={onDragLeave}
                          onDrop={onDrop}
                          className={`block cursor-pointer rounded-xl border-2 border-dashed px-4 py-5 transition ${
                            isDragActive
                              ? 'border-[var(--oc-accent)] bg-white shadow-[0_0_0_4px_rgba(15,118,110,0.08)]'
                              : 'border-[var(--oc-border)] bg-white hover:border-[var(--oc-accent)]'
                          }`}
                        >
                          <input
                            id="upload-file"
                            type="file"
                            accept=".csv,.txt,.xls,.xlsx"
                            className="hidden"
                            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                          />
                          <p className="text-sm font-semibold text-[var(--oc-accent-ink)]">{file ? file.name : isDragActive ? 'Drop file here' : 'Choose a file to upload'}</p>
                          <p className="mt-1 text-xs text-[var(--oc-muted)]">Drag and drop or click. Table refreshes after parse completes.</p>
                        </label>
                        <button
                          type="submit"
                          disabled={!file || isUploading}
                          className="inline-flex items-center justify-center rounded-xl bg-[var(--oc-accent)] px-5 py-3 text-sm font-bold text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isUploading ? 'Uploading...' : 'Upload and Parse'}
                        </button>
                      </div>
                    </form>
                  )}
                </div>

                <div className="mt-4 overflow-x-auto">
                  {isCompaniesLoading ? (
                    <p className="py-6 text-sm text-[var(--oc-muted)]">Loading companies...</p>
                  ) : !companies || companies.items.length === 0 ? (
                    <p className="py-6 text-sm text-[var(--oc-muted)]">No companies in this view.</p>
                  ) : (
                    <>
                      <table className="oc-compact-table min-w-[960px]">
                        <thead>
                          <tr>
                            <th className="w-10">
                              <input
                                type="checkbox"
                                checked={allVisibleSelected}
                                onChange={toggleVisibleSelection}
                                className="h-4 w-4 rounded border-[var(--oc-border)]"
                              />
                            </th>
                            <th>Domain</th>
                            <th>Decision</th>
                            <th>Scrape</th>
                            <th className="w-[220px]">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {companies.items.map((item) => {
                            const scrapeBadge = scrapeBadgeForCompany(item)
                            return (
                              <tr key={item.id}>
                                <td className="w-10">
                                  <input
                                    type="checkbox"
                                    checked={selectedCompanyIds.includes(item.id)}
                                    onChange={() => toggleCompanySelection(item.id)}
                                    className="h-4 w-4 rounded border-[var(--oc-border)]"
                                  />
                                </td>
                                <td title={`${item.domain}\n${item.raw_url}\n${item.normalized_url}`}>
                                  <span className="block max-w-[360px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)]">
                                    {item.domain}
                                  </span>
                                </td>
                                <td>
                                  {item.latest_decision ? (
                                    <span className={`oc-badge ${decisionBadgeClass(item.latest_decision)}`}>{item.latest_decision}</span>
                                  ) : (
                                    <span className="oc-badge oc-badge-neutral">No decision</span>
                                  )}
                                </td>
                                <td title={scrapeBadge.title}>
                                  <span className={scrapeBadge.className}>{scrapeBadge.label}</span>
                                </td>
                                <td>
                                  <div className="flex items-center gap-2">
                                    <button
                                      type="button"
                                      onClick={() => void onScrape(item)}
                                      disabled={item.latest_scrape_terminal === false}
                                      className="rounded-lg bg-[var(--oc-accent)] px-3 py-1.5 text-xs font-bold text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      Scrape
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => void onClassify(item)}
                                      disabled={
                                        !selectedPrompt ||
                                        !selectedPrompt.enabled ||
                                        item.latest_scrape_status !== 'completed' ||
                                        item.latest_analysis_terminal === false
                                      }
                                      className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      {item.latest_analysis_terminal === false ? 'Classifying...' : 'Classify'}
                                    </button>
                                    <span className="text-[11px] text-[var(--oc-muted)]">
                                      {analysisActionState[item.id] || actionState[item.id] || ''}
                                    </span>
                                  </div>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                      <div className="mt-3 flex justify-end">{renderPager()}</div>
                    </>
                  )}
                </div>
              </>
            ) : activeView === 'jobs' ? (
              <>
                <div className="oc-toolbar">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-bold tracking-tight">Scrape Jobs</h2>
                      <p className="mt-1 text-sm text-[var(--oc-muted)]">Live queue view. Active jobs auto-refresh every 4 seconds.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void loadScrapeJobs(jobsOffset, jobsPageSize)}
                        disabled={isJobsLoading}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isJobsLoading ? 'Refreshing...' : 'Refresh'}
                      </button>
                      <label className="text-xs font-semibold text-[var(--oc-muted)]">
                        Rows
                        <select
                          value={jobsPageSize}
                          onChange={(event) => setJobsPageSize(Number(event.target.value))}
                          className="ml-2 rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1 text-xs font-semibold text-[var(--oc-text)]"
                        >
                          {JOBS_PAGE_SIZE_OPTIONS.map((size) => (
                            <option key={size} value={size}>
                              {size}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        onClick={() => void loadScrapeJobs(Math.max(jobsOffset - jobsPageSize, 0), jobsPageSize)}
                        disabled={jobsOffset === 0 || isJobsLoading}
                        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Prev
                      </button>
                      <button
                        type="button"
                        onClick={() => void loadScrapeJobs(jobsOffset + jobsPageSize, jobsPageSize)}
                        disabled={!jobsHasMore || isJobsLoading}
                        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Next
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {JOB_FILTERS.map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        onClick={() => {
                          setJobsFilter(item.value)
                          setJobsOffset(0)
                        }}
                        className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                          jobsFilter === item.value
                            ? 'bg-[var(--oc-accent)] text-white'
                            : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                    <span className="oc-kbd">{jobsRangeLabel}</span>
                  </div>
                </div>

                <div className="mt-4 overflow-x-auto">
                  {isJobsLoading && scrapeJobs.length === 0 ? (
                    <p className="py-6 text-sm text-[var(--oc-muted)]">Loading scrape jobs…</p>
                  ) : scrapeJobs.length === 0 ? (
                    <p className="py-6 text-sm text-[var(--oc-muted)]">No scrape jobs in this view.</p>
                  ) : (
                    <table className="oc-compact-table min-w-[980px]">
                      <thead>
                        <tr>
                          <th>Job</th>
                          <th>Domain</th>
                          <th>Status</th>
                          <th>Stage 1</th>
                          <th>Stage 2</th>
                          <th>Pages</th>
                          <th>Error</th>
                          <th>Updated</th>
                          <th>View</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scrapeJobs.map((job) => {
                          const badge = badgeForJob(job)
                          return (
                            <tr key={job.id}>
                              <td className="font-mono text-[11px] text-[var(--oc-muted)]" title={job.id}>
                                {job.id.slice(0, 8)}...
                              </td>
                              <td title={job.normalized_url}>
                                <span className="block max-w-[240px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)]">
                                  {job.domain}
                                </span>
                              </td>
                              <td>
                                <span className={badge.className}>{badge.label}</span>
                              </td>
                              <td className="text-[12px] text-[var(--oc-muted)]">{job.stage1_status}</td>
                              <td className="text-[12px] text-[var(--oc-muted)]">{job.stage2_status}</td>
                              <td className="text-[12px] tabular-nums text-[var(--oc-muted)]">
                                {job.pages_fetched_count > 0 ? (
                                  <span title={`${job.pages_fetched_count} fetched, ${job.markdown_pages_count} with markdown`}>
                                    <span className={job.markdown_pages_count > 0 ? 'font-semibold text-[var(--oc-text)]' : ''}>
                                      {job.markdown_pages_count}
                                    </span>
                                    <span className="text-[var(--oc-border)]">/{job.pages_fetched_count}</span>
                                  </span>
                                ) : (
                                  <span className="text-[var(--oc-border)]">—</span>
                                )}
                              </td>
                              <td className="text-[12px] text-[var(--oc-muted)]">{job.last_error_code ?? '-'}</td>
                              <td className="text-[12px] text-[var(--oc-muted)]">{new Date(job.updated_at).toLocaleString()}</td>
                              <td>
                                {(job.markdown_pages_count ?? 0) > 0 && (
                                  <button
                                    type="button"
                                    onClick={() => void openMarkdownDrawer(job)}
                                    className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                                  >
                                    View Markdown
                                  </button>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="oc-toolbar">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-bold tracking-tight">Analysis Runs</h2>
                      <p className="mt-1 text-sm text-[var(--oc-muted)]">
                        Classification progress grouped by upload. Active runs auto-refresh every 4 seconds.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void loadRuns(runsOffset, runsPageSize)}
                        disabled={isRunsLoading}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isRunsLoading ? 'Refreshing...' : 'Refresh'}
                      </button>
                      <label className="text-xs font-semibold text-[var(--oc-muted)]">
                        Rows
                        <select
                          value={runsPageSize}
                          onChange={(event) => setRunsPageSize(Number(event.target.value))}
                          className="ml-2 rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1 text-xs font-semibold text-[var(--oc-text)]"
                        >
                          {RUNS_PAGE_SIZE_OPTIONS.map((size) => (
                            <option key={size} value={size}>
                              {size}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        onClick={() => void loadRuns(Math.max(runsOffset - runsPageSize, 0), runsPageSize)}
                        disabled={runsOffset === 0 || isRunsLoading}
                        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Prev
                      </button>
                      <button
                        type="button"
                        onClick={() => void loadRuns(runsOffset + runsPageSize, runsPageSize)}
                        disabled={!runsHasMore || isRunsLoading}
                        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </div>

                <div className="mt-4 overflow-x-auto">
                  {isRunsLoading && runs.length === 0 ? (
                    <p className="py-6 text-sm text-[var(--oc-muted)]">Loading analysis runs…</p>
                  ) : runs.length === 0 ? (
                    <p className="py-6 text-sm text-[var(--oc-muted)]">No analysis runs yet.</p>
                  ) : (
                    <table className="oc-compact-table min-w-[920px]">
                      <thead>
                        <tr>
                          <th>Run</th>
                          <th>Prompt</th>
                          <th>Status</th>
                          <th>Progress</th>
                          <th>Failed</th>
                          <th>Created</th>
                          <th>Inspect</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runs.map((run) => {
                          const badge = runBadge(run)
                          return (
                            <tr key={run.id}>
                              <td className="font-mono text-[11px] text-[var(--oc-muted)]" title={run.id}>
                                {run.id.slice(0, 8)}...
                              </td>
                              <td>
                                <span className="block max-w-[260px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)]">
                                  {run.prompt_name}
                                </span>
                              </td>
                              <td>
                                <span className={badge.className}>{badge.label}</span>
                              </td>
                              <td className="text-[12px] text-[var(--oc-muted)]">
                                {run.completed_jobs + run.failed_jobs}/{run.total_jobs}
                              </td>
                              <td className="text-[12px] text-[var(--oc-muted)]">{run.failed_jobs}</td>
                              <td className="text-[12px] text-[var(--oc-muted)]">{new Date(run.created_at).toLocaleString()}</td>
                              <td>
                                <button
                                  type="button"
                                  onClick={() => void loadRunJobs(run)}
                                  className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                                >
                                  Inspect
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </>
            )}
          </section>
        </section>

        <div aria-live="polite" aria-atomic="true">
          {error && (
            <section className="oc-panel border-[var(--oc-danger-bg)] bg-[var(--oc-danger-bg)] p-4">
              <p className="font-medium text-[var(--oc-danger-text)]">{error}</p>
            </section>
          )}
          {notice && (
            <section className="oc-panel border-emerald-200 bg-emerald-50 p-4">
              <p className="font-medium text-emerald-800">{notice}</p>
            </section>
          )}
        </div>

        {markdownJob && (
          <div className="fixed inset-0 z-40 bg-slate-950/18 backdrop-blur-[1px]">
            <div className="absolute inset-y-0 right-0 w-full max-w-[720px] border-l border-[var(--oc-border)] bg-[var(--oc-surface-strong)] shadow-[0_18px_60px_rgba(10,31,24,0.18)] md:w-[48vw]">
              <div className="flex h-full flex-col">
                <div className="border-b border-[var(--oc-border)] px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Markdown Review</p>
                      <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-[var(--oc-text)]">{markdownJob.domain}</h2>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <span className={badgeForJob(markdownJob).className}>{badgeForJob(markdownJob).label}</span>
                        <span className="text-xs text-[var(--oc-muted)]">{new Date(markdownJob.updated_at).toLocaleString()}</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={closeMarkdownDrawer}
                      className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                    >
                      Close
                    </button>
                  </div>

                  {!isMarkdownLoading && markdownPages.length > 0 && (
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      {markdownPages.map((page) => (
                        <button
                          key={page.id}
                          type="button"
                          onClick={() => setActiveMarkdownPageKind(page.page_kind)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                            activeMarkdownPageKind === page.page_kind
                              ? 'bg-[var(--oc-accent)] text-white'
                              : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                          }`}
                        >
                          {PAGE_KIND_LABELS[page.page_kind as keyof typeof PAGE_KIND_LABELS] ?? page.page_kind}
                        </button>
                      ))}
                      {activeMarkdownPage && (
                        <button
                          type="button"
                          onClick={() => void copyMarkdown(activeMarkdownPage.markdown_content)}
                          className="ml-auto rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                        >
                          {markdownCopyState || 'Copy Markdown'}
                        </button>
                      )}
                    </div>
                  )}
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4" style={{ overscrollBehavior: 'contain' }}>
                  {isMarkdownLoading ? (
                    <p className="text-sm text-[var(--oc-muted)]">Loading markdown…</p>
                  ) : markdownError ? (
                    <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                      <p className="text-sm text-[var(--oc-muted)]">{markdownError}</p>
                    </div>
                  ) : activeMarkdownPage ? (
                    <div className="space-y-3">
                      <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] px-4 py-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                          {PAGE_KIND_LABELS[activeMarkdownPage.page_kind as keyof typeof PAGE_KIND_LABELS] ?? activeMarkdownPage.page_kind}
                        </p>
                        <p className="mt-2 truncate text-sm font-semibold text-[var(--oc-accent-ink)]" title={activeMarkdownPage.url}>
                          {activeMarkdownPage.url}
                        </p>
                      </div>
                      <article className="oc-markdown rounded-2xl border border-[var(--oc-border)] bg-white p-5">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {activeMarkdownPage.markdown_content}
                        </ReactMarkdown>
                      </article>
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                      <p className="text-sm text-[var(--oc-muted)]">Markdown not generated for this page.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {promptSheetOpen && (
          <div className="fixed inset-0 z-40 bg-slate-950/18 backdrop-blur-[1px]">
            <div className="absolute inset-y-0 right-0 w-full max-w-[860px] border-l border-[var(--oc-border)] bg-[var(--oc-surface-strong)] shadow-[0_18px_60px_rgba(10,31,24,0.18)] xl:w-[56vw]">
              <div className="flex h-full flex-col">
                <div className="border-b border-[var(--oc-border)] px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Prompt Library</p>
                      <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-[var(--oc-text)]">
                        {selectedPrompt ? selectedPrompt.name : 'Prompt control'}
                      </h2>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {selectedPrompt ? (
                          <span className={`oc-badge ${selectedPrompt.enabled ? 'oc-badge-success' : 'oc-badge-fail'}`}>
                            {selectedPrompt.enabled ? 'Selected for future runs' : 'Selected but disabled'}
                          </span>
                        ) : (
                          <span className="oc-badge oc-badge-neutral">No prompt selected</span>
                        )}
                        <button
                          type="button"
                          onClick={() => void loadPrompts(selectedPromptId, editingPromptId !== null)}
                          disabled={isPromptsLoading}
                          className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {isPromptsLoading ? 'Refreshing...' : 'Refresh'}
                        </button>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={closePromptSheet}
                      className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                    >
                      Close
                    </button>
                  </div>
                </div>

                <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto] xl:grid-cols-[300px_minmax(0,1fr)] xl:grid-rows-1">
                  <aside className="min-h-0 border-b border-[var(--oc-border)] p-4 xl:border-b-0 xl:border-r">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <h3 className="text-sm font-bold tracking-tight">Saved prompts</h3>
                      <button
                        type="button"
                        onClick={onNewPrompt}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                      >
                        New blank
                      </button>
                    </div>
                    <div className="h-full max-h-[280px] space-y-2 overflow-y-auto pr-1 xl:max-h-none">
                      {isPromptsLoading && prompts.length === 0 ? (
                        <p className="text-sm text-[var(--oc-muted)]">Loading prompts...</p>
                      ) : prompts.length === 0 ? (
                        <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                          <p className="text-sm text-[var(--oc-muted)]">No prompts saved yet.</p>
                        </div>
                      ) : (
                        prompts.map((prompt) => (
                          <div
                            key={prompt.id}
                            className={`rounded-2xl border p-3 transition ${
                              editingPromptId === prompt.id
                                ? 'border-[var(--oc-accent)] bg-[var(--oc-accent-soft)]/50'
                                : 'border-[var(--oc-border)] bg-[var(--oc-surface)]'
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => onSelectPrompt(prompt)}
                              className="block w-full text-left"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-bold text-[var(--oc-accent-ink)]">{prompt.name}</p>
                                  <p className="mt-1 text-[11px] text-[var(--oc-muted)]">
                                    {new Date(prompt.created_at).toLocaleString()}
                                  </p>
                                </div>
                                {selectedPromptId === prompt.id ? (
                                  <span className="oc-badge oc-badge-info">Selected</span>
                                ) : null}
                              </div>
                            </button>
                            <div className="mt-3 flex items-center justify-between gap-2">
                              <span className={`oc-badge ${prompt.enabled ? 'oc-badge-success' : 'oc-badge-fail'}`}>
                                {prompt.enabled ? 'Enabled' : 'Disabled'}
                              </span>
                              <button
                                type="button"
                                onClick={() => void onTogglePromptEnabled(prompt)}
                                disabled={isPromptSaving}
                                className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-[11px] font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {prompt.enabled ? 'Disable' : 'Enable'}
                              </button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </aside>

                  <section className="min-h-0 overflow-y-auto p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-bold tracking-tight">
                          {editingPromptId ? 'Edit prompt' : 'Create prompt'}
                        </h3>
                        <p className="mt-1 text-sm text-[var(--oc-muted)]">
                          Save new versions by default. Update current only for small corrections.
                        </p>
                      </div>
                      {editingPromptId ? (
                        <span className="oc-kbd">editing current</span>
                      ) : (
                        <span className="oc-kbd">new draft</span>
                      )}
                    </div>

                    <div className="mt-5 space-y-4">
                      <label className="block">
                        <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                          Name
                        </span>
                        <input
                          type="text"
                          value={promptName}
                          onChange={(event) => setPromptName(event.target.value)}
                          className="w-full rounded-xl border border-[var(--oc-border)] bg-white px-4 py-3 text-sm text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)]"
                          placeholder="Supplier fit rubric v1"
                        />
                      </label>

                      <label className="block">
                        <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                          Prompt text
                        </span>
                        <textarea
                          value={promptText}
                          onChange={(event) => setPromptText(event.target.value)}
                          className="min-h-[320px] w-full rounded-2xl border border-[var(--oc-border)] bg-white px-4 py-3 text-sm leading-7 text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)]"
                          placeholder="Paste or write the rubric prompt here."
                        />
                      </label>

                      <label className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--oc-text)]">
                        <input
                          type="checkbox"
                          checked={promptEnabled}
                          onChange={(event) => setPromptEnabled(event.target.checked)}
                          className="h-4 w-4 rounded border-[var(--oc-border)]"
                        />
                        Enabled
                      </label>
                    </div>

                    {promptError ? (
                      <div className="mt-4 rounded-2xl border border-[var(--oc-danger-bg)] bg-[var(--oc-danger-bg)] p-4">
                        <p className="text-sm font-medium text-[var(--oc-danger-text)]">{promptError}</p>
                      </div>
                    ) : null}

                    <div className="mt-5 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void onSavePromptAsNew()}
                        disabled={isPromptSaving}
                        className="rounded-lg bg-[var(--oc-accent)] px-4 py-2 text-sm font-bold text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isPromptSaving ? 'Saving...' : 'Save as new'}
                      </button>
                      <button
                        type="button"
                        onClick={() => void onUpdateCurrentPrompt()}
                        disabled={!editingPromptId || isPromptSaving}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-4 py-2 text-sm font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Update current
                      </button>
                      <button
                        type="button"
                        onClick={onNewPrompt}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-4 py-2 text-sm font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                      >
                        New blank
                      </button>
                    </div>
                  </section>
                </div>
              </div>
            </div>
          </div>
        )}

        {inspectedRun && (
          <div className="fixed inset-0 z-40 bg-slate-950/18 backdrop-blur-[1px]">
            <div className="absolute inset-y-0 right-0 w-full max-w-[860px] border-l border-[var(--oc-border)] bg-[var(--oc-surface-strong)] shadow-[0_18px_60px_rgba(10,31,24,0.18)] xl:w-[56vw]">
              <div className="flex h-full flex-col">
                <div className="border-b border-[var(--oc-border)] px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                        {analysisDetail ? 'Classification Evidence' : 'Run Inspection'}
                      </p>
                      <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-[var(--oc-text)]">
                        {analysisDetail ? analysisDetail.domain : inspectedRun.prompt_name}
                      </h2>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {analysisDetail ? (
                          <>
                            <span className={decisionBadgeForLabel(analysisDetail.predicted_label)}>
                              {analysisDetail.predicted_label ?? 'No result'}
                            </span>
                            <span className={analysisStateBadge(analysisDetail.state, analysisDetail.terminal_state).className}>
                              {analysisStateBadge(analysisDetail.state, analysisDetail.terminal_state).label}
                            </span>
                            <span className="text-xs text-[var(--oc-muted)]">
                              Confidence {analysisDetail.confidence !== null ? analysisDetail.confidence.toFixed(2) : '-'}
                            </span>
                          </>
                        ) : (
                          <>
                            <span className={runBadge(inspectedRun).className}>{runBadge(inspectedRun).label}</span>
                            <span className="text-xs text-[var(--oc-muted)]">
                              {inspectedRun.completed_jobs + inspectedRun.failed_jobs}/{inspectedRun.total_jobs}
                            </span>
                            <span className="text-xs text-[var(--oc-muted)]">
                              {new Date(inspectedRun.created_at).toLocaleString()}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {analysisDetail ? (
                        <button
                          type="button"
                          onClick={() => {
                            setAnalysisDetail(null)
                            setAnalysisDetailError('')
                          }}
                          className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                        >
                          Back
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={closeRunDrawer}
                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                      >
                        Close
                      </button>
                    </div>
                  </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                  {isAnalysisDetailLoading ? (
                    <p className="text-sm text-[var(--oc-muted)]">Loading evidence...</p>
                  ) : analysisDetailError ? (
                    <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                      <p className="text-sm text-[var(--oc-muted)]">{analysisDetailError}</p>
                    </div>
                  ) : !analysisDetail ? (
                    <>
                      <div className="mb-4 rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                        <div className="grid gap-3 md:grid-cols-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Prompt</p>
                            <p className="mt-2 text-sm font-semibold text-[var(--oc-accent-ink)]">{inspectedRun.prompt_name}</p>
                          </div>
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Progress</p>
                            <p className="mt-2 text-sm font-semibold text-[var(--oc-accent-ink)]">
                              {inspectedRun.completed_jobs + inspectedRun.failed_jobs}/{inspectedRun.total_jobs}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Failures</p>
                            <p className="mt-2 text-sm font-semibold text-[var(--oc-accent-ink)]">{inspectedRun.failed_jobs}</p>
                          </div>
                        </div>
                      </div>

                      {isRunJobsLoading ? (
                        <p className="text-sm text-[var(--oc-muted)]">Loading run jobs...</p>
                      ) : runJobsError ? (
                        <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                          <p className="text-sm text-[var(--oc-muted)]">{runJobsError}</p>
                        </div>
                      ) : runJobs.length === 0 ? (
                        <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                          <p className="text-sm text-[var(--oc-muted)]">No jobs found for this run.</p>
                        </div>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="oc-compact-table min-w-[760px]">
                            <thead>
                              <tr>
                                <th>Domain</th>
                                <th>Result</th>
                                <th>State</th>
                                <th>Confidence</th>
                                <th>Inspect</th>
                              </tr>
                            </thead>
                            <tbody>
                              {runJobs.map((job) => {
                                const badge = analysisStateBadge(job.state, job.terminal_state)
                                return (
                                  <tr key={job.analysis_job_id}>
                                    <td>
                                      <span className="block max-w-[260px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)]">
                                        {job.domain}
                                      </span>
                                    </td>
                                    <td>
                                      <span className={decisionBadgeForLabel(job.predicted_label)}>
                                        {job.predicted_label ?? 'No result'}
                                      </span>
                                    </td>
                                    <td>
                                      <span className={badge.className}>{badge.label}</span>
                                    </td>
                                    <td className="text-[12px] text-[var(--oc-muted)]">
                                      {job.confidence !== null ? job.confidence.toFixed(2) : '-'}
                                    </td>
                                    <td>
                                      <button
                                        type="button"
                                        onClick={() => void openAnalysisDetail(job)}
                                        className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                                      >
                                        Inspect
                                      </button>
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="space-y-4">
                      <section className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={decisionBadgeForLabel(analysisDetail.predicted_label)}>
                            {analysisDetail.predicted_label ?? 'No result'}
                          </span>
                          <span className={analysisStateBadge(analysisDetail.state, analysisDetail.terminal_state).className}>
                            {analysisStateBadge(analysisDetail.state, analysisDetail.terminal_state).label}
                          </span>
                          <span className="text-xs text-[var(--oc-muted)]">Prompt {analysisDetail.prompt_name}</span>
                        </div>
                        {analysisDetail.last_error_code ? (
                          <p className="mt-3 text-sm text-[var(--oc-fail-text)]">
                            {analysisDetail.last_error_code}: {analysisDetail.last_error_message || 'No detail'}
                          </p>
                        ) : null}
                      </section>

                      <section className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Evidence</p>
                        <div className="mt-3 space-y-3">
                          {evidenceItems.length > 0 ? (
                            evidenceItems.map((item, index) => (
                              <blockquote key={`${index}:${item.slice(0, 24)}`} className="rounded-r-xl border-l-4 border-[var(--oc-accent)] bg-[var(--oc-accent-soft)]/35 px-4 py-3 text-sm leading-7 text-[var(--oc-text)]">
                                {item}
                              </blockquote>
                            ))
                          ) : (
                            <p className="text-sm text-[var(--oc-muted)]">No evidence captured for this job.</p>
                          )}
                        </div>
                      </section>

                      <section className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Signals</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {Object.keys(reasoningSignals).length > 0 ? (
                            Object.entries(reasoningSignals).map(([key, value]) => (
                              <span key={key} className="rounded-full border border-[var(--oc-border)] bg-[var(--oc-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--oc-text)]">
                                {key}: {typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}
                              </span>
                            ))
                          ) : (
                            <p className="text-sm text-[var(--oc-muted)]">No signals recorded.</p>
                          )}
                        </div>
                      </section>

                      <section className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Other Fields</p>
                        <div className="mt-3 space-y-3">
                          {Object.keys(reasoningOtherFields).length > 0 ? (
                            Object.entries(reasoningOtherFields).map(([key, value]) => (
                              <div key={key} className="grid gap-1 border-b border-[var(--oc-border)] pb-3 last:border-b-0 last:pb-0">
                                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--oc-muted)]">{key}</p>
                                <p className="text-sm leading-7 text-[var(--oc-text)]">{String(value)}</p>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-[var(--oc-muted)]">No additional fields recorded.</p>
                          )}
                        </div>
                      </section>

                      <details className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
                        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                          Raw Model Output
                        </summary>
                        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl bg-white p-4 text-xs leading-6 text-[var(--oc-text)]">
                          {rawModelOutput || 'No raw model output stored.'}
                        </pre>
                      </details>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
