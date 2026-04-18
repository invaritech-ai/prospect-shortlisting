import { useCallback, useState, type Dispatch, type SetStateAction } from 'react'
import type {
  AnalysisJobDetailRead,
  AnalysisRunJobRead,
  CompanyListItem,
  ManualLabel,
  RunRead,
  ScrapeJobRead,
  ScrapePageContentRead,
} from '../lib/types'
import {
  getScrapeJob,
  getAnalysisJobDetail,
  listRunJobs,
  listScrapeJobPageContents,
  upsertCompanyFeedback,
} from '../lib/api'
import { canRenderScrapeJobPanel, resolveScrapeJobRead } from '../lib/scrapeJobResolution'
import { parseApiError } from '../lib/utils'

export interface UsePanelsResult {
  // Markdown preview
  markdownJob: ScrapeJobRead | null
  markdownPages: ScrapePageContentRead[]
  activeMarkdownPageKind: string
  isMarkdownLoading: boolean
  markdownError: string
  markdownCopyState: string
  openMarkdownDrawer: (job: ScrapeJobRead) => Promise<void>
  openMarkdownFromDiagnostics: (job: ScrapeJobRead) => Promise<void>
  closeMarkdownDrawer: () => void
  setActiveMarkdownPageKind: (k: string) => void
  copyMarkdown: (content: string) => Promise<void>
  // Scrape diagnostics
  diagnosticsJob: ScrapeJobRead | null
  diagnosticsPages: ScrapePageContentRead[]
  isDiagnosticsLoading: boolean
  diagnosticsError: string
  openScrapeDiagnostics: (job: ScrapeJobRead) => Promise<void>
  closeScrapeDiagnostics: () => void
  // Company review
  reviewedCompany: CompanyListItem | null
  companyReviewDetail: AnalysisJobDetailRead | null
  isCompanyReviewLoading: boolean
  companyReviewError: string
  isFeedbackSaving: boolean
  openCompanyReview: (company: CompanyListItem) => Promise<void>
  closeCompanyReview: () => void
  saveFeedback: (thumbs: 'up' | 'down' | null, comment: string) => Promise<void>
  setManualLabelOnReviewed: (label: ManualLabel | null) => void
  // Analysis detail
  inspectedRun: RunRead | null
  runJobs: AnalysisRunJobRead[]
  isRunJobsLoading: boolean
  runJobsError: string
  analysisDetail: AnalysisJobDetailRead | null
  isAnalysisDetailLoading: boolean
  analysisDetailError: string
  loadRunJobs: (run: RunRead) => Promise<void>
  openAnalysisDetail: (job: AnalysisRunJobRead) => Promise<void>
  closeRunDrawer: () => void
  setAnalysisDetail: Dispatch<SetStateAction<AnalysisJobDetailRead | null>>
  setAnalysisDetailError: Dispatch<SetStateAction<string>>
}

export function usePanels(
  setError: (e: string) => void,
  setNotice: (n: string) => void,
  onFeedbackSaved?: () => void,
): UsePanelsResult {
  // ── Markdown preview ──────────────────────────────────────────────────────
  const [markdownJob, setMarkdownJob] = useState<ScrapeJobRead | null>(null)
  const [markdownPages, setMarkdownPages] = useState<ScrapePageContentRead[]>([])
  const [activeMarkdownPageKind, setActiveMarkdownPageKind] = useState('')
  const [isMarkdownLoading, setIsMarkdownLoading] = useState(false)
  const [markdownError, setMarkdownError] = useState('')
  const [markdownCopyState, setMarkdownCopyState] = useState('')

  // ── Scrape diagnostics ────────────────────────────────────────────────────
  const [diagnosticsJob, setDiagnosticsJob] = useState<ScrapeJobRead | null>(null)
  const [diagnosticsPages, setDiagnosticsPages] = useState<ScrapePageContentRead[]>([])
  const [isDiagnosticsLoading, setIsDiagnosticsLoading] = useState(false)
  const [diagnosticsError, setDiagnosticsError] = useState('')

  // ── Company review ────────────────────────────────────────────────────────
  const [reviewedCompany, setReviewedCompany] = useState<CompanyListItem | null>(null)
  const [companyReviewDetail, setCompanyReviewDetail] = useState<AnalysisJobDetailRead | null>(null)
  const [isCompanyReviewLoading, setIsCompanyReviewLoading] = useState(false)
  const [companyReviewError, setCompanyReviewError] = useState('')
  const [isFeedbackSaving, setIsFeedbackSaving] = useState(false)

  // ── Analysis detail ───────────────────────────────────────────────────────
  const [inspectedRun, setInspectedRun] = useState<RunRead | null>(null)
  const [runJobs, setRunJobsState] = useState<AnalysisRunJobRead[]>([])
  const [isRunJobsLoading, setIsRunJobsLoading] = useState(false)
  const [runJobsError, setRunJobsError] = useState('')
  const [analysisDetail, setAnalysisDetail] = useState<AnalysisJobDetailRead | null>(null)
  const [isAnalysisDetailLoading, setIsAnalysisDetailLoading] = useState(false)
  const [analysisDetailError, setAnalysisDetailError] = useState('')

  // ── Markdown handlers ─────────────────────────────────────────────────────
  const loadMarkdownDrawer = useCallback(async (
    job: ScrapeJobRead,
    initialJob: ScrapeJobRead | null = null,
  ) => {
    setMarkdownPages([]); setActiveMarkdownPageKind(''); setMarkdownError(''); setMarkdownCopyState('')
    setMarkdownJob(initialJob)
    setIsMarkdownLoading(true)
    try {
      const hydratedJob = initialJob ?? await resolveScrapeJobRead(job, getScrapeJob)
      setMarkdownJob(hydratedJob)
      const pages = await listScrapeJobPageContents(job.id)
      const withContent = pages.filter((p) => p.markdown_content.trim().length > 0)
      const filtered = withContent.sort((a, b) => {
        if (a.page_kind === 'home') return -1
        if (b.page_kind === 'home') return 1
        return a.page_kind.localeCompare(b.page_kind)
      })
      setMarkdownPages(filtered)
      setActiveMarkdownPageKind(filtered[0]?.page_kind ?? '')
      if (filtered.length === 0) setMarkdownError('No markdown available for this scrape job.')
    } catch (err) {
      setMarkdownJob((current) => current ?? initialJob)
      setMarkdownError(parseApiError(err))
    }
    finally { setIsMarkdownLoading(false) }
  }, [])

  const openMarkdownDrawer = useCallback(async (job: ScrapeJobRead) => {
    const initialJob = canRenderScrapeJobPanel(job) ? job : null
    await loadMarkdownDrawer(job, initialJob)
  }, [loadMarkdownDrawer])

  const openMarkdownFromDiagnostics = useCallback(async (job: ScrapeJobRead) => {
    setDiagnosticsJob(null); setDiagnosticsPages([]); setDiagnosticsError(''); setIsDiagnosticsLoading(false)
    const initialJob = canRenderScrapeJobPanel(job) ? job : null
    await loadMarkdownDrawer(job, initialJob)
  }, [loadMarkdownDrawer])

  const closeMarkdownDrawer = useCallback(() => {
    setMarkdownJob(null); setMarkdownPages([]); setActiveMarkdownPageKind('')
    setMarkdownError(''); setMarkdownCopyState('')
  }, [])

  const copyMarkdown = useCallback(async (content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setMarkdownCopyState('Copied')
    } catch {
      setMarkdownCopyState('Copy failed')
    }
    window.setTimeout(() => setMarkdownCopyState(''), 1600)
  }, [])

  // ── Diagnostics handlers ──────────────────────────────────────────────────
  const openScrapeDiagnostics = useCallback(async (job: ScrapeJobRead) => {
    setDiagnosticsPages([]); setDiagnosticsError(''); setIsDiagnosticsLoading(true)
    try {
      const hydratedJob = await resolveScrapeJobRead(job, getScrapeJob)
      setDiagnosticsJob(hydratedJob)
      const pages = await listScrapeJobPageContents(job.id)
      setDiagnosticsPages(pages)
    } catch (err) {
      setDiagnosticsJob(null)
      setDiagnosticsError(parseApiError(err))
    }
    finally { setIsDiagnosticsLoading(false) }
  }, [])

  const closeScrapeDiagnostics = useCallback(() => {
    setDiagnosticsJob(null); setDiagnosticsPages([]); setDiagnosticsError('')
  }, [])

  // ── Company review handlers ───────────────────────────────────────────────
  const openCompanyReview = useCallback(async (company: CompanyListItem) => {
    setReviewedCompany(company)
    setCompanyReviewDetail(null); setCompanyReviewError('')
    if (company.latest_analysis_job_id) {
      setIsCompanyReviewLoading(true)
      try {
        const detail = await getAnalysisJobDetail(company.latest_analysis_job_id)
        setCompanyReviewDetail(detail)
      } catch (err) { setCompanyReviewError(parseApiError(err)) }
      finally { setIsCompanyReviewLoading(false) }
    }
  }, [])

  const closeCompanyReview = useCallback(() => {
    setReviewedCompany(null); setCompanyReviewDetail(null); setCompanyReviewError('')
  }, [])

  const saveFeedback = useCallback(async (thumbs: 'up' | 'down' | null, comment: string) => {
    if (!reviewedCompany) return
    setIsFeedbackSaving(true)
    try {
      await upsertCompanyFeedback(reviewedCompany.id, {
        thumbs,
        comment: comment || null,
        manual_label: reviewedCompany.feedback_manual_label ?? null,
      })
      setReviewedCompany((prev) =>
        prev ? { ...prev, feedback_thumbs: thumbs, feedback_comment: comment || null } : prev,
      )
      setNotice('Feedback saved.')
      onFeedbackSaved?.()
    } catch (err) { setError(parseApiError(err)) }
    finally { setIsFeedbackSaving(false) }
  }, [reviewedCompany, setError, setNotice, onFeedbackSaved])

  const setManualLabelOnReviewed = useCallback((label: ManualLabel | null) => {
    setReviewedCompany((prev) =>
      prev ? { ...prev, feedback_manual_label: label } : prev,
    )
  }, [])

  // ── Analysis detail handlers ──────────────────────────────────────────────
  const loadRunJobs = useCallback(async (run: RunRead) => {
    setInspectedRun(run); setRunJobsState([]); setAnalysisDetail(null)
    setRunJobsError(''); setAnalysisDetailError(''); setIsRunJobsLoading(true)
    try {
      const rows = await listRunJobs(run.id)
      setRunJobsState(rows)
    } catch (err) { setRunJobsError(parseApiError(err)) }
    finally { setIsRunJobsLoading(false) }
  }, [])

  const openAnalysisDetail = useCallback(async (job: AnalysisRunJobRead) => {
    setAnalysisDetail(null); setAnalysisDetailError(''); setIsAnalysisDetailLoading(true)
    try {
      const detail = await getAnalysisJobDetail(job.analysis_job_id)
      setAnalysisDetail(detail)
    } catch (err) { setAnalysisDetailError(parseApiError(err)) }
    finally { setIsAnalysisDetailLoading(false) }
  }, [])

  const closeRunDrawer = useCallback(() => {
    setInspectedRun(null); setRunJobsState([]); setAnalysisDetail(null)
    setRunJobsError(''); setAnalysisDetailError('')
  }, [])

  return {
    markdownJob, markdownPages, activeMarkdownPageKind, isMarkdownLoading,
    markdownError, markdownCopyState,
    openMarkdownDrawer, openMarkdownFromDiagnostics, closeMarkdownDrawer, setActiveMarkdownPageKind, copyMarkdown,
    diagnosticsJob, diagnosticsPages, isDiagnosticsLoading, diagnosticsError,
    openScrapeDiagnostics, closeScrapeDiagnostics,
    reviewedCompany, companyReviewDetail, isCompanyReviewLoading, companyReviewError,
    isFeedbackSaving, openCompanyReview, closeCompanyReview, saveFeedback, setManualLabelOnReviewed,
    inspectedRun, runJobs, isRunJobsLoading, runJobsError,
    analysisDetail, isAnalysisDetailLoading, analysisDetailError,
    loadRunJobs, openAnalysisDetail, closeRunDrawer,
    setAnalysisDetail, setAnalysisDetailError,
  }
}
