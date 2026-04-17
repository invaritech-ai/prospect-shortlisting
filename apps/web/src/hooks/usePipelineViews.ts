import { useCallback, useEffect, useState } from 'react'
import type { ActiveView } from '../lib/navigation'
import type {
  CompanyList,
  CompanyStageFilter,
  ContactListResponse,
  ContactStageFilter,
  DecisionFilter,
  PromptRead,
  S4VerifFilter,
  ScrapeFilter,
  ScrapeSubFilter,
} from '../lib/types'
import {
  createRuns,
  fetchContactsSelected,
  getLetterCounts,
  listCompanies,
  listCompanyIds,
  listContacts,
  scrapeSelectedCompanies,
  verifyContacts,
} from '../lib/api'
import { getPipelineCompanyQuery } from '../lib/pipelineQuery'
import { parseApiError } from '../lib/utils'

// Map UI scrape sub-filter to the server-side ScrapeFilter param
function scrapeSubToFilter(sub: ScrapeSubFilter): ScrapeFilter {
  if (sub === 'pending') return 'none'
  if (sub === 'done') return 'done'
  if (sub === 'failed') return 'failed'
  return 'all' // 'all' and 'active' — server loads all, client filters for 'active'
}

// Map S4 verification filter to listContacts params
function verifFilterToParams(filter: S4VerifFilter): {
  verificationStatus?: string
  stageFilter?: ContactStageFilter
  titleMatch?: boolean
} {
  switch (filter) {
    case 'valid': return { verificationStatus: 'valid' }
    case 'invalid': return { verificationStatus: 'invalid' }
    case 'catch-all': return { verificationStatus: 'catch-all' }
    case 'unverified': return { verificationStatus: 'unverified' }
    case 'campaign_ready': return { stageFilter: 'campaign_ready' }
    case 'title_match': return { titleMatch: true }
    default: return {}
  }
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
  pipelineDecisionFilter: DecisionFilter
  pipelineScrapeSubFilter: ScrapeSubFilter
  pipelineSortBy: string
  pipelineSortDir: 'asc' | 'desc'
  onPipelineDecisionFilterChange: (filter: DecisionFilter) => void
  onPipelineScrapeSubFilterChange: (filter: ScrapeSubFilter) => void
  onPipelineSort: (field: string) => void
  // S4 flat contacts
  s4Contacts: ContactListResponse | null
  s4LetterCounts: Record<string, number>
  s4ActiveLetters: Set<string>
  s4SelectedContactIds: string[]
  s4VerifFilter: S4VerifFilter
  isS4Loading: boolean
  isS4Validating: boolean
  s4SortBy: string
  s4SortDir: 'asc' | 'desc'
  onS4Sort: (field: string) => void
  onS4VerifFilterChange: (filter: S4VerifFilter) => void
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
  onS4ToggleContact: (id: string) => void
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
  const [pipelineDecisionFilter, setPipelineDecisionFilter] = useState<DecisionFilter>('all')
  const [pipelineScrapeSubFilter, setPipelineScrapeSubFilter] = useState<ScrapeSubFilter>('pending')
  const [pipelineSortBy, setPipelineSortBy] = useState('domain')
  const [pipelineSortDir, setPipelineSortDir] = useState<'asc' | 'desc'>('asc')

  // Full pipeline state
  const [fullPipelineCompanies, setFullPipelineCompanies] = useState<CompanyList | null>(null)
  const [fullPipelineLetterCounts, setFullPipelineLetterCounts] = useState<Record<string, number>>({})
  const [fullPipelineActiveLetter, setFullPipelineActiveLetter] = useState<string | null>(null)
  const [fullPipelineSelectedIds, setFullPipelineSelectedIds] = useState<string[]>([])
  const [isFullPipelineLoading, setIsFullPipelineLoading] = useState(false)
  const [isFullPipelineScraping, setIsFullPipelineScraping] = useState(false)

  // S4 state
  const [s4Contacts, setS4Contacts] = useState<ContactListResponse | null>(null)
  const [s4LetterCounts, setS4LetterCounts] = useState<Record<string, number>>({})
  const [s4ActiveLetters, setS4ActiveLetters] = useState(new Set<string>())
  const [s4SelectedContactIds, setS4SelectedContactIds] = useState<string[]>([])
  const [s4VerifFilter, setS4VerifFilter] = useState<S4VerifFilter>('all')
  const [isS4Loading, setIsS4Loading] = useState(false)
  const [isS4Validating, setIsS4Validating] = useState(false)
  const [s4SortBy, setS4SortBy] = useState('domain')
  const [s4SortDir, setS4SortDir] = useState<'asc' | 'desc'>('asc')

  // ── Load functions ─────────────────────────────────────────────────────────

  const loadPipelineView = useCallback(
    async (
      stageFilter: CompanyStageFilter,
      decisionFilter: DecisionFilter,
      scrapeFilter: ScrapeFilter,
      sortBy = 'domain',
      sortDir: 'asc' | 'desc' = 'asc',
    ) => {
      setIsPipelineLoading(true)
      try {
        const [companies, letterCountsData] = await Promise.all([
          listCompanies(200, 0, decisionFilter, true, scrapeFilter, stageFilter, null, sortBy, sortDir),
          getLetterCounts(decisionFilter, scrapeFilter, stageFilter),
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

  const loadS4View = useCallback(async (
    sortBy = 'domain',
    sortDir: 'asc' | 'desc' = 'asc',
    verifFilter: S4VerifFilter = 'all',
  ) => {
    setIsS4Loading(true)
    try {
      const filterParams = verifFilterToParams(verifFilter)
      const data = await listContacts({ limit: 500, sortBy, sortDir, ...filterParams })
      setS4Contacts(data)
      const lc: Record<string, number> = {}
      for (const item of data.items) {
        const letter = item.domain?.[0]?.toLowerCase()
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
    const query = getPipelineCompanyQuery(activeView, 'all')
    if (query !== null) {
      const defaultScrapeSubFilter: ScrapeSubFilter = activeView === 's1-scraping' ? 'pending' : 'all'
      const defaultScrapeFilter = scrapeSubToFilter(defaultScrapeSubFilter)
      setPipelineSelectedIds([])
      setPipelineActiveLetters(new Set())
      setPipelineDecisionFilter('all')
      setPipelineScrapeSubFilter(defaultScrapeSubFilter)
      setPipelineSortBy('domain')
      setPipelineSortDir('asc')
      void loadPipelineView(query.stageFilter, query.decisionFilter, defaultScrapeFilter, 'domain', 'asc')
    } else if (activeView === 'full-pipeline') {
      setFullPipelineSelectedIds([])
      setFullPipelineActiveLetter(null)
      void loadFullPipelineView(null)
    } else if (activeView === 's4-validation') {
      setS4SelectedContactIds([])
      setS4ActiveLetters(new Set())
      setS4VerifFilter('all')
      setS4SortBy('domain')
      setS4SortDir('asc')
      void loadS4View('domain', 'asc', 'all')
    }
  }, [activeView, loadPipelineView, loadFullPipelineView, loadS4View])

  // ── S1–S3 handlers ─────────────────────────────────────────────────────────

  const onPipelineToggleLetter = useCallback((letter: string) => {
    setPipelineActiveLetters((prev) => {
      const next = new Set(prev)
      if (next.has(letter)) next.delete(letter)
      else next.add(letter)
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
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    setIsPipelineSelectingAll(true)
    try {
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      const letters = [...pipelineActiveLetters]
      const results = await Promise.all(
        letters.length > 0
          ? letters.map((l) => listCompanyIds(query.decisionFilter, sf, query.stageFilter, l))
          : [listCompanyIds(query.decisionFilter, sf, query.stageFilter, null)],
      )
      setPipelineSelectedIds([...new Set(results.flatMap((r) => r.ids.map((id) => String(id))))])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsPipelineSelectingAll(false)
    }
  }, [activeView, pipelineActiveLetters, pipelineDecisionFilter, pipelineScrapeSubFilter, setError])

  const onPipelineSelectAllMatching = useCallback(() => {
    void selectAllMatchingAsync()
  }, [selectAllMatchingAsync])

  const onPipelineClearSelection = useCallback(() => setPipelineSelectedIds([]), [])

  const onPipelineDecisionFilterChange = useCallback(
    (decisionFilter: DecisionFilter) => {
      const query = getPipelineCompanyQuery(activeView, decisionFilter)
      if (query === null) return
      setPipelineDecisionFilter(decisionFilter)
      setPipelineSelectedIds([])
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir)
    },
    [activeView, pipelineScrapeSubFilter, loadPipelineView, pipelineSortBy, pipelineSortDir],
  )

  const onPipelineScrapeSubFilterChange = useCallback(
    (sub: ScrapeSubFilter) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      setPipelineScrapeSubFilter(sub)
      setPipelineSelectedIds([])
      const sf = scrapeSubToFilter(sub)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir)
    },
    [activeView, pipelineDecisionFilter, loadPipelineView, pipelineSortBy, pipelineSortDir],
  )

  const onPipelineSort = useCallback(
    (field: string) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      const newDir: 'asc' | 'desc' =
        pipelineSortBy === field ? (pipelineSortDir === 'asc' ? 'desc' : 'asc') : 'asc'
      setPipelineSortBy(field)
      setPipelineSortDir(newDir)
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, field, newDir)
    },
    [activeView, pipelineDecisionFilter, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, loadPipelineView],
  )

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
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query !== null) {
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir)
    } else if (activeView === 'full-pipeline') {
      void loadFullPipelineView(fullPipelineActiveLetter)
    } else if (activeView === 's4-validation') {
      void loadS4View(s4SortBy, s4SortDir, s4VerifFilter)
    }
  }, [
    activeView,
    pipelineDecisionFilter,
    pipelineScrapeSubFilter,
    loadPipelineView,
    loadFullPipelineView,
    fullPipelineActiveLetter,
    loadS4View,
    pipelineSortBy,
    pipelineSortDir,
    s4SortBy,
    s4SortDir,
    s4VerifFilter,
  ])

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
      if (next.has(letter)) next.delete(letter)
      else next.add(letter)
      return next
    })
    setS4SelectedContactIds([])
  }, [])

  const onS4ClearLetters = useCallback(() => {
    setS4ActiveLetters(new Set())
    setS4SelectedContactIds([])
  }, [])

  const onS4ToggleContact = useCallback((id: string) => {
    setS4SelectedContactIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [])

  const onS4ToggleAll = useCallback((ids: string[]) => {
    if (ids.length === 0) {
      setS4SelectedContactIds([])
    } else {
      setS4SelectedContactIds((prev) => [...new Set([...prev, ...ids])])
    }
  }, [])

  const onS4ClearSelection = useCallback(() => setS4SelectedContactIds([]), [])

  const onS4VerifFilterChange = useCallback(
    (filter: S4VerifFilter) => {
      setS4VerifFilter(filter)
      setS4SelectedContactIds([])
      void loadS4View(s4SortBy, s4SortDir, filter)
    },
    [loadS4View, s4SortBy, s4SortDir],
  )

  const onS4Sort = useCallback(
    (field: string) => {
      const newDir: 'asc' | 'desc' =
        s4SortBy === field ? (s4SortDir === 'asc' ? 'desc' : 'asc') : 'asc'
      setS4SortBy(field)
      setS4SortDir(newDir)
      void loadS4View(field, newDir, s4VerifFilter)
    },
    [s4SortBy, s4SortDir, s4VerifFilter, loadS4View],
  )

  const validateSelectedAsync = useCallback(async () => {
    if (!s4SelectedContactIds.length) return
    setError('')
    setNotice('')
    setIsS4Validating(true)
    try {
      const result = await verifyContacts({ contact_ids: s4SelectedContactIds })
      setNotice(result.message)
      setS4SelectedContactIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsS4Validating(false)
    }
  }, [s4SelectedContactIds, setError, setNotice])

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
    pipelineDecisionFilter,
    pipelineScrapeSubFilter,
    pipelineSortBy,
    pipelineSortDir,
    onPipelineDecisionFilterChange,
    onPipelineScrapeSubFilterChange,
    onPipelineSort,
    s4Contacts,
    s4LetterCounts,
    s4ActiveLetters,
    s4SelectedContactIds,
    s4VerifFilter,
    isS4Loading,
    isS4Validating,
    s4SortBy,
    s4SortDir,
    onS4Sort,
    onS4VerifFilterChange,
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
    onS4ToggleContact,
    onS4ToggleAll,
    onS4ClearSelection,
    onS4ValidateSelected,
  }
}
