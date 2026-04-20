import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  assignUploadsToCampaign,
  createCampaign,
  createRuns,
  createScrapeJob,
  deleteCampaign,
  drainQueue,
  fetchContactsForCompany,
  fetchContactsForCompanyApollo,
  getContactsExportUrl,
  getCampaignCosts,
  getCompanyCounts,
  getContactCounts,
  getPipelineRunProgress,
  getStats,
  listRuns,
  listScrapeJobs,
  listCampaigns,
  listUploads,
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
} from './lib/types'
import type { ActiveView } from './lib/navigation'
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

function App() {
  const pollFailuresRef = useRef(0)

  // ── Navigation ────────────────────────────────────────────────────────────
  const [activeView, setActiveView] = useState<ActiveView>('dashboard')

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
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null)
  const [isCampaignLoading, setIsCampaignLoading] = useState(false)
  const [isCampaignSaving, setIsCampaignSaving] = useState(false)
  const [latestPipelineRunId, setLatestPipelineRunId] = useState<string | null>(null)
  const [latestPipelineRunProgress, setLatestPipelineRunProgress] = useState<PipelineRunProgressRead | null>(null)
  const [campaignCostSummary, setCampaignCostSummary] = useState<PipelineCostSummaryRead | null>(null)
  const activeCampaignName =
    campaigns.find((c) => c.id === selectedCampaignId)?.name ??
    campaigns[0]?.name ??
    null

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
    promptMgmt.selectedPrompt,
    scrapePromptMgmt.activeScrapePrompt,
    setError,
    setNotice,
  )

  const panels = usePanels(setError, setNotice, pipeline.refreshPipelineView)

  // ── Load functions ────────────────────────────────────────────────────────

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

  const loadContactCounts = useCallback(async () => {
    try {
      const data = await getContactCounts()
      setContactCounts(data)
    } catch { /* non-critical */ }
  }, [])

  const loadRecentActivity = useCallback(async () => {
    try {
      const [scrapeRows, runRows] = await Promise.all([
        listScrapeJobs(5, 0, 'all', ''),
        listRuns(5, 0),
      ])
      setRecentScrapeJobs(scrapeRows)
      setRecentRuns(runRows)
    } catch { /* non-critical */ }
  }, [])

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
    try {
      const summary = await getCampaignCosts(campaignId)
      setCampaignCostSummary(summary)
    } catch {
      // non-critical telemetry path
    }
  }, [])

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    void promptMgmt.loadPrompts()
    void scrapePromptMgmt.loadScrapePrompts()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void loadStats()
    void loadCompanyCounts()
    void loadContactCounts()
    void loadRecentActivity()
    void loadCampaignData()
    const timer = window.setInterval(() => {
      void loadStats()
      void loadCompanyCounts()
      void loadContactCounts()
    }, 10000)
    return () => window.clearInterval(timer)
  }, [loadStats, loadCompanyCounts, loadContactCounts, loadRecentActivity, loadCampaignData])

  useEffect(() => {
    void loadCampaignCostSummary(selectedCampaignId)
    setLatestPipelineRunId(null)
    setLatestPipelineRunProgress(null)
  }, [loadCampaignCostSummary, selectedCampaignId])

  useEffect(() => {
    if (!latestPipelineRunId) return
    let cancelled = false
    const loadProgress = async () => {
      try {
        const progress = await getPipelineRunProgress(latestPipelineRunId)
        if (!cancelled) setLatestPipelineRunProgress(progress)
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
  }, [latestPipelineRunId])

  useEffect(() => {
    if (!error) return
    setNotice('')
    setNoticeAction(null)
  }, [error])

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
      pipeline.refreshPipelineView()
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
      pipeline.refreshPipelineView()
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
    setError(''); setNotice('')
    try {
      const result = await fetchContactsForCompany(company.id)
      const msg = result.queued_count > 0
        ? `Queued contact fetch for ${company.domain}.`
        : result.already_fetching_count > 0
          ? `Contact fetch already in progress for ${company.domain}.`
          : `No contacts queued for ${company.domain}.`
      setNotice(msg)
    } catch (err) { setError(parseApiError(err)) }
  }

  const onFetchContactsApollo = async (company: CompanyListItem) => {
    setError(''); setNotice('')
    try {
      const result = await fetchContactsForCompanyApollo(company.id)
      const msg = result.queued_count > 0
        ? `Queued Apollo fetch for ${company.domain}.`
        : result.already_fetching_count > 0
          ? `Apollo fetch already in progress for ${company.domain}.`
          : `No Apollo contacts queued for ${company.domain}.`
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
      pipeline.refreshPipelineView()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsStartingCampaignPipeline(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <AppShell className="min-h-0 flex-1"
        activeView={activeView}
        setActiveView={setActiveView}
        activeCampaignName={activeCampaignName}
        stats={stats}
        onOpenPromptLibrary={activeView === 's1-scraping' ? scrapePromptMgmt.openScrapePromptSheet : promptMgmt.openPromptSheet}
      >
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
            onNavigate={(view) => setActiveView(view)}
          />
        )}

        {activeView === 'campaigns' && (
          <CampaignsView
            campaigns={campaigns}
            uploads={uploads}
            selectedCampaignId={selectedCampaignId}
            isLoading={isCampaignLoading}
            isSaving={isCampaignSaving}
            onSelectCampaign={setSelectedCampaignId}
            onCreateCampaign={(name, description) => void onCreateCampaign(name, description)}
            onDeleteCampaign={(campaignId) => void onDeleteCampaign(campaignId)}
            onAssignUploads={(campaignId, uploadIds) => void onAssignUploads(campaignId, uploadIds)}
            onStartCampaignPipeline={() => void onStartCampaignPipeline()}
            isStartingCampaignPipeline={isStartingCampaignPipeline}
            latestRunProgress={latestPipelineRunProgress}
            campaignCostSummary={campaignCostSummary}
          />
        )}

        {activeView === 'full-pipeline' && (
          <FullPipelineView
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
          />
        )}

        {activeView === 's1-scraping' && (
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

        {activeView === 's2-ai' && (
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

        {activeView === 's3-contacts' && (
          <S3ContactFetchView
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
              else { void onFetchContacts(c); void onFetchContactsApollo(c) }
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

        {activeView === 's4-validation' && (
          <S4ValidationView
            contacts={pipeline.s4Contacts}
            letterCounts={pipeline.s4LetterCounts}
            activeLetters={pipeline.s4ActiveLetters}
            verifFilter={pipeline.s4VerifFilter}
            selectedContactIds={pipeline.s4SelectedContactIds}
            totalMatching={pipeline.s4Contacts?.total ?? null}
            contactCounts={contactCounts}
            isLoading={pipeline.isS4Loading}
            isValidating={pipeline.isS4Validating}
            isSelectingAll={false}
            exportUrl={getContactsExportUrl()}
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
        isOpen={isTitleRulesOpen}
        onClose={() => setIsTitleRulesOpen(false)}
      />
    </>
  )
}

export default App
