import { useCallback, useEffect, useState } from 'react'
import type { ActiveView } from '../lib/navigation'
import type {
  CompanyList,
  CompanyStageFilter,
  ContactCompanyListResponse,
  PromptRead,
} from '../lib/types'
import {
  createRuns,
  fetchContactsSelected,
  getLetterCounts,
  listCompanies,
  listCompanyIds,
  listContactCompanies,
  scrapeSelectedCompanies,
  verifyContacts,
} from '../lib/api'
import { parseApiError } from '../lib/utils'

const PIPELINE_STAGE_MAP: Partial<Record<ActiveView, CompanyStageFilter>> = {
  's1-scraping': 'all',
  's2-ai': 'scraped',
  's3-contacts': 'classified',
}

export interface UsePipelineViewsResult {
  // Full pipeline view
  fullPipelineCompanies: CompanyList | null
  fullPipelineLetterCounts: Record<string, number>
  fullPipelineActiveLetter: string | null
  fullPipelineSelectedIds: string[]
  isFullPipelineLoading: boolean
  isFullPipelineScraping: boolean
  onFullPipelineLetterChange: (l: string | null) => void
  onFullPipelineToggleRow: (id: string) => void
  onFullPipelineToggleAll: (ids: string[]) => void
  onFullPipelineClearSelection: () => void
  onFullPipelineScrapeSelected: () => void
  // S1–S3 company list
  pipelineCompanies: CompanyList | null
  pipelineLetterCounts: Record<string, number>
  pipelineActiveLetters: Set<string>
  pipelineSelectedIds: string[]
  isPipelineLoading: boolean
  isPipelineScraping: boolean
  isPipelineAnalyzing: boolean
  isPipelineFetching: boolean
  isPipelineSelectingAll: boolean
  // S4 contact companies
  s4Companies: ContactCompanyListResponse | null
  s4LetterCounts: Record<string, number>
  s4ActiveLetters: Set<string>
  s4SelectedCompanyIds: string[]
  isS4Loading: boolean
  isS4Validating: boolean
  // S1–S3 handlers
  onPipelineToggleLetter: (l: string) => void
  onPipelineClearLetters: () => void
  onPipelineToggleRow: (id: string) => void
  onPipelineToggleAll: (ids: string[]) => void
  onPipelineSelectAllMatching: () => void
  onPipelineClearSelection: () => void
  onPipelineScrapeSelected: () => void
  onPipelineAnalyzeSelected: () => void
  onPipelineFetchContacts: (source: 'snov' | 'apollo' | 'both') => void
  refreshPipelineView: () => void
  // S4 handlers
  onS4ToggleLetter: (l: string) => void
  onS4ClearLetters: () => void
  onS4ToggleCompany: (id: string) => void
  onS4ToggleAll: (ids: string[]) => void
  onS4ClearSelection: () => void
  onS4ValidateSelected: () => void
}

export function usePipelineViews(
  activeView: ActiveView,
  selectedPrompt: PromptRead | null,
  setError: (e: string) => void,
  setNotice: (n: string) => void,
): UsePipelineViewsResult {
  // S1–S3 state
  const [pipelineCompanies, setPipelineCompanies] = useState<CompanyList | null>(null)
  const [pipelineLetterCounts, setPipelineLetterCounts] = useState<Record<string, number>>({})
  const [pipelineActiveLetters, setPipelineActiveLetters] = useState(new Set<string>())
  const [pipelineSelectedIds, setPipelineSelectedIds] = useState<string[]>([])
  const [isPipelineLoading, setIsPipelineLoading] = useState(false)
  const [isPipelineScraping, setIsPipelineScraping] = useState(false)
  const [isPipelineAnalyzing, setIsPipelineAnalyzing] = useState(false)
  const [isPipelineFetching, setIsPipelineFetching] = useState(false)
  const [isPipelineSelectingAll, setIsPipelineSelectingAll] = useState(false)

  // Full pipeline state
  const [fullPipelineCompanies, setFullPipelineCompanies] = useState<CompanyList | null>(null)
  const [fullPipelineLetterCounts, setFullPipelineLetterCounts] = useState<Record<string, number>>({})
  const [fullPipelineActiveLetter, setFullPipelineActiveLetter] = useState<string | null>(null)
  const [fullPipelineSelectedIds, setFullPipelineSelectedIds] = useState<string[]>([])
  const [isFullPipelineLoading, setIsFullPipelineLoading] = useState(false)
  const [isFullPipelineScraping, setIsFullPipelineScraping] = useState(false)

  // S4 state
  const [s4Companies, setS4Companies] = useState<ContactCompanyListResponse | null>(null)
  const [s4LetterCounts, setS4LetterCounts] = useState<Record<string, number>>({})
  const [s4ActiveLetters, setS4ActiveLetters] = useState(new Set<string>())
  const [s4SelectedCompanyIds, setS4SelectedCompanyIds] = useState<string[]>([])
  const [isS4Loading, setIsS4Loading] = useState(false)
  const [isS4Validating, setIsS4Validating] = useState(false)

  // ── Load functions ─────────────────────────────────────────────────────────

  const loadPipelineView = useCallback(
    async (stageFilter: CompanyStageFilter) => {
      setIsPipelineLoading(true)
      try {
        const [companies, letterCountsData] = await Promise.all([
          listCompanies(200, 0, 'all', true, 'all', stageFilter),
          getLetterCounts('all', 'all', stageFilter),
        ])
        setPipelineCompanies(companies)
        setPipelineLetterCounts(letterCountsData.counts)
      } catch (err) {
        setError(parseApiError(err))
      } finally {
        setIsPipelineLoading(false)
      }
    },
    [setError],
  )

  const loadS4View = useCallback(async () => {
    setIsS4Loading(true)
    try {
      const companiesData = await listContactCompanies({ limit: 200 })
      setS4Companies(companiesData)
      const lc: Record<string, number> = {}
      for (const item of companiesData.items) {
        const letter = item.domain[0]?.toLowerCase()
        if (letter) lc[letter] = (lc[letter] ?? 0) + 1
      }
      setS4LetterCounts(lc)
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsS4Loading(false)
    }
  }, [setError])

  const loadFullPipelineView = useCallback(
    async (letter: string | null) => {
      setIsFullPipelineLoading(true)
      try {
        const [companies, letterCountsData] = await Promise.all([
          listCompanies(200, 0, 'all', true, 'all', 'all', letter),
          getLetterCounts('all', 'all', 'all'),
        ])
        setFullPipelineCompanies(companies)
        setFullPipelineLetterCounts(letterCountsData.counts)
      } catch (err) {
        setError(parseApiError(err))
      } finally {
        setIsFullPipelineLoading(false)
      }
    },
    [setError],
  )

  // ── Load on view change ────────────────────────────────────────────────────
  useEffect(() => {
    const stageFilter = PIPELINE_STAGE_MAP[activeView]
    if (stageFilter !== undefined) {
      setPipelineSelectedIds([])
      setPipelineActiveLetters(new Set())
      void loadPipelineView(stageFilter)
    } else if (activeView === 'full-pipeline') {
      setFullPipelineSelectedIds([])
      setFullPipelineActiveLetter(null)
      void loadFullPipelineView(null)
    } else if (activeView === 's4-validation') {
      setS4SelectedCompanyIds([])
      setS4ActiveLetters(new Set())
      void loadS4View()
    }
  }, [activeView, loadPipelineView, loadFullPipelineView, loadS4View])

  // ── S1–S3 handlers ─────────────────────────────────────────────────────────

  const onPipelineToggleLetter = useCallback((letter: string) => {
    setPipelineActiveLetters((prev) => {
      const next = new Set(prev)
      next.has(letter) ? next.delete(letter) : next.add(letter)
      return next
    })
    setPipelineSelectedIds([])
  }, [])

  const onPipelineClearLetters = useCallback(() => {
    setPipelineActiveLetters(new Set())
    setPipelineSelectedIds([])
  }, [])

  const onPipelineToggleRow = useCallback((id: string) => {
    setPipelineSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [])

  const onPipelineToggleAll = useCallback((ids: string[]) => {
    if (ids.length === 0) {
      setPipelineSelectedIds([])
    } else {
      setPipelineSelectedIds((prev) => [...new Set([...prev, ...ids])])
    }
  }, [])

  const selectAllMatchingAsync = useCallback(async () => {
    const stageFilter = PIPELINE_STAGE_MAP[activeView]
    if (!stageFilter) return
    setIsPipelineSelectingAll(true)
    try {
      const letters = [...pipelineActiveLetters]
      const results = await Promise.all(
        letters.length > 0
          ? letters.map((l) => listCompanyIds('all', 'all', stageFilter, l))
          : [listCompanyIds('all', 'all', stageFilter, null)],
      )
      setPipelineSelectedIds([...new Set(results.flatMap((r) => r.ids.map((id) => String(id))))])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsPipelineSelectingAll(false)
    }
  }, [activeView, pipelineActiveLetters, setError])

  const onPipelineSelectAllMatching = useCallback(() => {
    void selectAllMatchingAsync()
  }, [selectAllMatchingAsync])

  const onPipelineClearSelection = useCallback(() => setPipelineSelectedIds([]), [])

  const scrapeSelectedAsync = useCallback(async () => {
    if (!pipelineSelectedIds.length) return
    setError('')
    setNotice('')
    setIsPipelineScraping(true)
    try {
      const result = await scrapeSelectedCompanies(pipelineSelectedIds)
      setNotice(`Queued ${result.queued_count} scrape job${result.queued_count === 1 ? '' : 's'}.`)
      setPipelineSelectedIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsPipelineScraping(false)
    }
  }, [pipelineSelectedIds, setError, setNotice])

  const onPipelineScrapeSelected = useCallback(() => {
    void scrapeSelectedAsync()
  }, [scrapeSelectedAsync])

  const analyzeSelectedAsync = useCallback(async () => {
    if (!pipelineSelectedIds.length || !selectedPrompt?.enabled) {
      setError('Select an enabled prompt before running analysis.')
      return
    }
    setError('')
    setNotice('')
    setIsPipelineAnalyzing(true)
    try {
      const result = await createRuns({
        prompt_id: selectedPrompt.id,
        scope: 'selected',
        company_ids: pipelineSelectedIds,
      })
      setNotice(
        `Created ${result.runs.length} run${result.runs.length === 1 ? '' : 's'}, queued ${result.queued_count}/${result.requested_count} classifications.`,
      )
      setPipelineSelectedIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsPipelineAnalyzing(false)
    }
  }, [pipelineSelectedIds, selectedPrompt, setError, setNotice])

  const onPipelineAnalyzeSelected = useCallback(() => {
    void analyzeSelectedAsync()
  }, [analyzeSelectedAsync])

  const fetchContactsAsync = useCallback(
    async (source: 'snov' | 'apollo' | 'both') => {
      if (!pipelineSelectedIds.length) return
      setError('')
      setNotice('')
      setIsPipelineFetching(true)
      try {
        const result = await fetchContactsSelected(pipelineSelectedIds, source)
        setNotice(
          `Queued contact fetch for ${result.queued_count} compan${result.queued_count === 1 ? 'y' : 'ies'} via ${source}.`,
        )
        setPipelineSelectedIds([])
      } catch (err) {
        setError(parseApiError(err))
      } finally {
        setIsPipelineFetching(false)
      }
    },
    [pipelineSelectedIds, setError, setNotice],
  )

  const onPipelineFetchContacts = useCallback(
    (source: 'snov' | 'apollo' | 'both') => {
      void fetchContactsAsync(source)
    },
    [fetchContactsAsync],
  )

  const refreshPipelineView = useCallback(() => {
    const stageFilter = PIPELINE_STAGE_MAP[activeView]
    if (stageFilter !== undefined) void loadPipelineView(stageFilter)
    else if (activeView === 'full-pipeline') void loadFullPipelineView(fullPipelineActiveLetter)
    else if (activeView === 's4-validation') void loadS4View()
  }, [activeView, loadPipelineView, loadFullPipelineView, fullPipelineActiveLetter, loadS4View])

  // ── Full pipeline handlers ─────────────────────────────────────────────────

  const onFullPipelineLetterChange = useCallback((letter: string | null) => {
    setFullPipelineActiveLetter(letter)
    setFullPipelineSelectedIds([])
    void loadFullPipelineView(letter)
  }, [loadFullPipelineView])

  const onFullPipelineToggleRow = useCallback((id: string) => {
    setFullPipelineSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [])

  const onFullPipelineToggleAll = useCallback((ids: string[]) => {
    if (ids.length === 0) {
      setFullPipelineSelectedIds([])
    } else {
      setFullPipelineSelectedIds((prev) => [...new Set([...prev, ...ids])])
    }
  }, [])

  const onFullPipelineClearSelection = useCallback(() => setFullPipelineSelectedIds([]), [])

  const fullPipelineScrapeAsync = useCallback(async () => {
    if (!fullPipelineSelectedIds.length) return
    setError('')
    setNotice('')
    setIsFullPipelineScraping(true)
    try {
      const result = await scrapeSelectedCompanies(fullPipelineSelectedIds)
      setNotice(`Queued ${result.queued_count} scrape job${result.queued_count === 1 ? '' : 's'}.`)
      setFullPipelineSelectedIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsFullPipelineScraping(false)
    }
  }, [fullPipelineSelectedIds, setError, setNotice])

  const onFullPipelineScrapeSelected = useCallback(() => {
    void fullPipelineScrapeAsync()
  }, [fullPipelineScrapeAsync])

  // ── S4 handlers ────────────────────────────────────────────────────────────

  const onS4ToggleLetter = useCallback((letter: string) => {
    setS4ActiveLetters((prev) => {
      const next = new Set(prev)
      next.has(letter) ? next.delete(letter) : next.add(letter)
      return next
    })
    setS4SelectedCompanyIds([])
  }, [])

  const onS4ClearLetters = useCallback(() => {
    setS4ActiveLetters(new Set())
    setS4SelectedCompanyIds([])
  }, [])

  const onS4ToggleCompany = useCallback((id: string) => {
    setS4SelectedCompanyIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [])

  const onS4ToggleAll = useCallback((ids: string[]) => {
    if (ids.length === 0) {
      setS4SelectedCompanyIds([])
    } else {
      setS4SelectedCompanyIds((prev) => [...new Set([...prev, ...ids])])
    }
  }, [])

  const onS4ClearSelection = useCallback(() => setS4SelectedCompanyIds([]), [])

  const validateSelectedAsync = useCallback(async () => {
    if (!s4SelectedCompanyIds.length) return
    setError('')
    setNotice('')
    setIsS4Validating(true)
    try {
      const result = await verifyContacts({ company_ids: s4SelectedCompanyIds })
      setNotice(result.message)
      setS4SelectedCompanyIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsS4Validating(false)
    }
  }, [s4SelectedCompanyIds, setError, setNotice])

  const onS4ValidateSelected = useCallback(() => {
    void validateSelectedAsync()
  }, [validateSelectedAsync])

  return {
    fullPipelineCompanies,
    fullPipelineLetterCounts,
    fullPipelineActiveLetter,
    fullPipelineSelectedIds,
    isFullPipelineLoading,
    isFullPipelineScraping,
    onFullPipelineLetterChange,
    onFullPipelineToggleRow,
    onFullPipelineToggleAll,
    onFullPipelineClearSelection,
    onFullPipelineScrapeSelected,
    pipelineCompanies,
    pipelineLetterCounts,
    pipelineActiveLetters,
    pipelineSelectedIds,
    isPipelineLoading,
    isPipelineScraping,
    isPipelineAnalyzing,
    isPipelineFetching,
    isPipelineSelectingAll,
    s4Companies,
    s4LetterCounts,
    s4ActiveLetters,
    s4SelectedCompanyIds,
    isS4Loading,
    isS4Validating,
    onPipelineToggleLetter,
    onPipelineClearLetters,
    onPipelineToggleRow,
    onPipelineToggleAll,
    onPipelineSelectAllMatching,
    onPipelineClearSelection,
    onPipelineScrapeSelected,
    onPipelineAnalyzeSelected,
    onPipelineFetchContacts,
    refreshPipelineView,
    onS4ToggleLetter,
    onS4ClearLetters,
    onS4ToggleCompany,
    onS4ToggleAll,
    onS4ClearSelection,
    onS4ValidateSelected,
  }
}
