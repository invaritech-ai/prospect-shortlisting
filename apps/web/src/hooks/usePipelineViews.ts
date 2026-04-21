import { useCallback, useEffect, useRef, useState } from 'react'
import type { ActiveView } from '../lib/navigation'
import type {
  CompanyListItem,
  CompanyList,
  CompanyStageFilter,
  ContactListResponse,
  DecisionFilter,
  ManualLabel,
  PromptRead,
  ScrapePromptRead,
  S4VerifFilter,
  ScrapeFilter,
  ScrapeSubFilter,
} from '../lib/types'
import {
  consumeCompanyListLegacySortFallback,
  consumeContactsListLegacySortFallback,
  consumeSortCompatUserNotice,
  createRuns,
  fetchContactsSelected,
  getLetterCounts,
  listCompanies,
  listCompanyIds,
  listContacts,
  scrapeSelectedCompanies,
  startPipelineRun,
  upsertCompanyFeedback,
  verifyContacts,
} from '../lib/api'
import { matchesFullPipelineFilters } from '../lib/fullPipelineFilters'
import type { FullPipelineStatusFilter } from '../lib/fullPipelineFilters'
import { getDefaultPipelineScrapeSubFilter } from '../lib/pipelineDefaults'
import { getResumeStageForCompany, scrapeSubToFilter, verifFilterToParams } from '../lib/pipelineMappings'
import { getPipelineCompanyQuery } from '../lib/pipelineQuery'
import { parseApiError } from '../lib/utils'

/** New sort on these fields defaults to descending (most recent first). */
const SORT_DESC_FIRST = new Set(['last_activity', 'updated_at', 'created_at'])

export const PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const
export const DEFAULT_PAGE_SIZE = 50

export interface UsePipelineViewsResult {
  // Full pipeline view
  fullPipelineCompanies: CompanyList | null
  fullPipelineLetterCounts: Record<string, number>
  fullPipelineActiveLetter: string | null
  fullPipelineSelectedIds: string[]
  fullPipelineResumeState: Record<string, string>
  fullPipelineOffset: number
  fullPipelinePageSize: number
  isFullPipelineLoading: boolean
  isFullPipelineScraping: boolean
  isFullPipelineSelectingAllMatching: boolean
  onFullPipelineLetterChange: (l: string | null) => void
  onFullPipelineToggleRow: (id: string) => void
  onFullPipelineToggleAll: (ids: string[]) => void
  onFullPipelineClearSelection: () => void
  onFullPipelineScrapeSelected: () => void
  onFullPipelineResumeCompany: (company: CompanyListItem) => void
  onFullPipelinePagePrev: () => void
  onFullPipelinePageNext: () => void
  onFullPipelinePageSizeChange: (size: number) => void
  onFullPipelineSelectAllMatching: (statusFilter: FullPipelineStatusFilter, search: string) => void
  fullPipelineSortBy: string
  fullPipelineSortDir: 'asc' | 'desc'
  onFullPipelineSort: (field: string) => void
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
  pipelineOffset: number
  pipelinePageSize: number
  pipelineSortBy: string
  pipelineSortDir: 'asc' | 'desc'
  onPipelineDecisionFilterChange: (filter: DecisionFilter) => void
  onPipelineScrapeSubFilterChange: (filter: ScrapeSubFilter) => void
  onPipelinePagePrev: () => void
  onPipelinePageNext: () => void
  onPipelinePageSizeChange: (size: number) => void
  onPipelineSort: (field: string) => void
  // S4 flat contacts
  s4Contacts: ContactListResponse | null
  s4LetterCounts: Record<string, number>
  s4ActiveLetters: Set<string>
  s4SelectedContactIds: string[]
  s4VerifFilter: S4VerifFilter
  s4Offset: number
  s4PageSize: number
  isS4Loading: boolean
  isS4Validating: boolean
  s4SortBy: string
  s4SortDir: 'asc' | 'desc'
  onS4Sort: (field: string) => void
  onS4VerifFilterChange: (filter: S4VerifFilter) => void
  onS4PagePrev: () => void
  onS4PageNext: () => void
  onS4PageSizeChange: (size: number) => void
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
  pipelineManualLabelActionState: Record<string, string>
  onPipelineSetManualLabel: (company: CompanyListItem, label: ManualLabel | null) => void
  refreshPipelineView: (options?: { background?: boolean }) => void
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
  selectedCampaignId: string | null,
  selectedPrompt: PromptRead | null,
  selectedScrapePrompt: ScrapePromptRead | null,
  requestsEnabled: boolean,
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
  const [pipelineManualLabelActionState, setPipelineManualLabelActionState] = useState<Record<string, string>>({})
  const [pipelineScrapeSubFilter, setPipelineScrapeSubFilter] = useState<ScrapeSubFilter>(() => getDefaultPipelineScrapeSubFilter(activeView))
  const [pipelineOffset, setPipelineOffset] = useState(0)
  const [pipelinePageSize, setPipelinePageSize] = useState(DEFAULT_PAGE_SIZE)
  const [pipelineSortBy, setPipelineSortBy] = useState('last_activity')
  const [pipelineSortDir, setPipelineSortDir] = useState<'asc' | 'desc'>('desc')

  // Full pipeline state
  const [fullPipelineCompanies, setFullPipelineCompanies] = useState<CompanyList | null>(null)
  const [fullPipelineLetterCounts, setFullPipelineLetterCounts] = useState<Record<string, number>>({})
  const [fullPipelineActiveLetter, setFullPipelineActiveLetter] = useState<string | null>(null)
  const [fullPipelineSelectedIds, setFullPipelineSelectedIds] = useState<string[]>([])
  const [fullPipelineResumeState, setFullPipelineResumeState] = useState<Record<string, string>>({})
  const [fullPipelineOffset, setFullPipelineOffset] = useState(0)
  const [fullPipelinePageSize, setFullPipelinePageSize] = useState(DEFAULT_PAGE_SIZE)
  const [fullPipelineSortBy, setFullPipelineSortBy] = useState('last_activity')
  const [fullPipelineSortDir, setFullPipelineSortDir] = useState<'asc' | 'desc'>('desc')
  const [isFullPipelineLoading, setIsFullPipelineLoading] = useState(false)
  const [isFullPipelineSelectingAllMatching, setIsFullPipelineSelectingAllMatching] = useState(false)
  const [isFullPipelineScraping, setIsFullPipelineScraping] = useState(false)

  // S4 state
  const [s4Contacts, setS4Contacts] = useState<ContactListResponse | null>(null)
  const [s4LetterCounts, setS4LetterCounts] = useState<Record<string, number>>({})
  const [s4ActiveLetters, setS4ActiveLetters] = useState(new Set<string>())
  const [s4SelectedContactIds, setS4SelectedContactIds] = useState<string[]>([])
  const [s4VerifFilter, setS4VerifFilter] = useState<S4VerifFilter>('all')
  const [s4Offset, setS4Offset] = useState(0)
  const [s4PageSize, setS4PageSize] = useState(DEFAULT_PAGE_SIZE)
  const [isS4Loading, setIsS4Loading] = useState(false)
  const [isS4Validating, setIsS4Validating] = useState(false)
  const [s4SortBy, setS4SortBy] = useState('updated_at')
  const [s4SortDir, setS4SortDir] = useState<'asc' | 'desc'>('desc')
  const pipelineRequestRef = useRef(0)
  const pipelineForegroundRequestRef = useRef(0)
  const s4RequestRef = useRef(0)
  const s4ForegroundRequestRef = useRef(0)
  const fullPipelineRequestRef = useRef(0)
  const fullPipelineForegroundRequestRef = useRef(0)
  const skipNextPipelineLetterReloadRef = useRef(false)
  const skipNextS4LetterReloadRef = useRef(false)

  // ── Load functions ─────────────────────────────────────────────────────────

  const loadPipelineView = useCallback(
    async (
      stageFilter: CompanyStageFilter,
      decisionFilter: DecisionFilter,
      scrapeFilter: ScrapeFilter,
      sortBy: string,
      sortDir: 'asc' | 'desc',
      pageSize: number,
      offset: number,
      letters: string[] = [],
      options?: { background?: boolean },
    ) => {
      if (!requestsEnabled || !selectedCampaignId) {
        pipelineRequestRef.current += 1
        setPipelineCompanies(null)
        setPipelineLetterCounts({})
        setIsPipelineLoading(false)
        return
      }
      const requestId = pipelineRequestRef.current + 1
      pipelineRequestRef.current = requestId
      const background = options?.background === true
      if (!background) {
        pipelineForegroundRequestRef.current = requestId
        setIsPipelineLoading(true)
      }
      try {
        const [companies, letterCountsData] = await Promise.all([
          listCompanies(selectedCampaignId, pageSize, offset, decisionFilter, true, scrapeFilter, stageFilter, null, sortBy, sortDir, undefined, letters),
          getLetterCounts(selectedCampaignId, decisionFilter, scrapeFilter, stageFilter),
        ])
        if (pipelineRequestRef.current !== requestId) return
        setPipelineCompanies(companies)
        setPipelineLetterCounts(letterCountsData.counts)
        if (consumeCompanyListLegacySortFallback()) {
          setPipelineSortBy('domain')
          setPipelineSortDir('asc')
        }
        const sortNotice = consumeSortCompatUserNotice()
        if (sortNotice) setNotice(sortNotice)
      } catch (err) {
        if (pipelineRequestRef.current !== requestId) return
        setError(parseApiError(err))
      } finally {
        if (!background && pipelineForegroundRequestRef.current === requestId) {
          setIsPipelineLoading(false)
        }
      }
    },
    [requestsEnabled, selectedCampaignId, setError, setNotice],
  )

  const loadS4View = useCallback(async (
    sortBy: string,
    sortDir: 'asc' | 'desc',
    verifFilter: S4VerifFilter,
    pageSize: number,
    offset: number,
    letters: string[] = [],
    options?: { background?: boolean },
  ) => {
    if (!requestsEnabled || !selectedCampaignId) {
      s4RequestRef.current += 1
      setS4Contacts(null)
      setS4LetterCounts({})
      setIsS4Loading(false)
      return
    }
    const requestId = s4RequestRef.current + 1
    s4RequestRef.current = requestId
    const background = options?.background === true
    if (!background) {
      s4ForegroundRequestRef.current = requestId
      setIsS4Loading(true)
    }
    try {
      const filterParams = verifFilterToParams(verifFilter)
      const [data, letterCountsData] = await Promise.all([
        listContacts({ campaignId: selectedCampaignId, limit: pageSize, offset, sortBy, sortDir, letters, ...filterParams }),
        listContacts({
          campaignId: selectedCampaignId,
          limit: 1,
          offset: 0,
          sortBy: 'domain',
          sortDir: 'asc',
          letters: [],
          countByLetters: true,
          ...filterParams,
        }),
      ])
      if (s4RequestRef.current !== requestId) return
      setS4Contacts(data)
      setS4LetterCounts(letterCountsData.letter_counts ?? {})
      if (consumeContactsListLegacySortFallback()) {
        setS4SortBy('domain')
        setS4SortDir('asc')
      }
      const sortNotice = consumeSortCompatUserNotice()
      if (sortNotice) setNotice(sortNotice)
    } catch (err) {
      if (s4RequestRef.current !== requestId) return
      setError(parseApiError(err))
    } finally {
      if (!background && s4ForegroundRequestRef.current === requestId) {
        setIsS4Loading(false)
      }
    }
  }, [requestsEnabled, selectedCampaignId, setError, setNotice])

  const loadFullPipelineView = useCallback(
    async (
      letter: string | null,
      pageSize: number,
      offset: number,
      sortBy: string,
      sortDir: 'asc' | 'desc',
      options?: { background?: boolean },
    ) => {
      if (!requestsEnabled || !selectedCampaignId) {
        fullPipelineRequestRef.current += 1
        setFullPipelineCompanies(null)
        setFullPipelineLetterCounts({})
        setIsFullPipelineLoading(false)
        return
      }
      const requestId = fullPipelineRequestRef.current + 1
      fullPipelineRequestRef.current = requestId
      const background = options?.background === true
      if (!background) {
        fullPipelineForegroundRequestRef.current = requestId
        setIsFullPipelineLoading(true)
      }
      try {
        const [companies, letterCountsData] = await Promise.all([
          listCompanies(selectedCampaignId, pageSize, offset, 'all', true, 'all', 'all', letter, sortBy, sortDir),
          getLetterCounts(selectedCampaignId, 'all', 'all', 'all'),
        ])
        if (fullPipelineRequestRef.current !== requestId) return
        setFullPipelineCompanies(companies)
        setFullPipelineLetterCounts(letterCountsData.counts)
        if (consumeCompanyListLegacySortFallback()) {
          setFullPipelineSortBy('domain')
          setFullPipelineSortDir('asc')
        }
        const sortNotice = consumeSortCompatUserNotice()
        if (sortNotice) setNotice(sortNotice)
      } catch (err) {
        if (fullPipelineRequestRef.current !== requestId) return
        setError(parseApiError(err))
      } finally {
        if (!background && fullPipelineForegroundRequestRef.current === requestId) {
          setIsFullPipelineLoading(false)
        }
      }
    },
    [requestsEnabled, selectedCampaignId, setError, setNotice],
  )

  // ── Load on view change ────────────────────────────────────────────────────
  useEffect(() => {
    const defaultDecisionFilter: DecisionFilter = activeView === 's3-contacts' ? 'labeled' : 'all'
    const query = getPipelineCompanyQuery(activeView, defaultDecisionFilter)
    if (query !== null) {
      const defaultScrapeSubFilter = getDefaultPipelineScrapeSubFilter(activeView)
      const defaultScrapeFilter = scrapeSubToFilter(defaultScrapeSubFilter)
      setPipelineSelectedIds([])
      skipNextPipelineLetterReloadRef.current = true
      setPipelineActiveLetters(new Set())
      setPipelineDecisionFilter(defaultDecisionFilter)
      setPipelineManualLabelActionState({})
      setPipelineScrapeSubFilter(defaultScrapeSubFilter)
      setPipelineOffset(0)
      setPipelinePageSize(DEFAULT_PAGE_SIZE)
      setPipelineSortBy('last_activity')
      setPipelineSortDir('desc')
      void loadPipelineView(query.stageFilter, query.decisionFilter, defaultScrapeFilter, 'last_activity', 'desc', DEFAULT_PAGE_SIZE, 0, [])
    } else if (activeView === 'full-pipeline') {
      setFullPipelineSelectedIds([])
      setFullPipelineActiveLetter(null)
      setFullPipelineOffset(0)
      setFullPipelinePageSize(DEFAULT_PAGE_SIZE)
      setFullPipelineSortBy('last_activity')
      setFullPipelineSortDir('desc')
      void loadFullPipelineView(null, DEFAULT_PAGE_SIZE, 0, 'last_activity', 'desc')
    } else if (activeView === 's4-validation') {
      setS4SelectedContactIds([])
      skipNextS4LetterReloadRef.current = true
      setS4ActiveLetters(new Set())
      setS4VerifFilter('valid')
      setS4Offset(0)
      setS4PageSize(DEFAULT_PAGE_SIZE)
      setS4SortBy('updated_at')
      setS4SortDir('desc')
      void loadS4View('updated_at', 'desc', 'valid', DEFAULT_PAGE_SIZE, 0, [])
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
    setPipelineSelectedIds(ids)
  }, [])

  const selectAllMatchingAsync = useCallback(async () => {
    if (!selectedCampaignId) return
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    setIsPipelineSelectingAll(true)
    try {
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      const letters = [...pipelineActiveLetters]
      const result = await listCompanyIds(
        selectedCampaignId,
        query.decisionFilter,
        sf,
        query.stageFilter,
        null,
        undefined,
        letters.length > 0 ? letters : undefined,
      )
      setPipelineSelectedIds(result.ids.map((id) => String(id)))
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsPipelineSelectingAll(false)
    }
  }, [activeView, pipelineActiveLetters, pipelineDecisionFilter, pipelineScrapeSubFilter, selectedCampaignId, setError])

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
      setPipelineOffset(0)
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, 0, [...pipelineActiveLetters])
    },
    [activeView, pipelineScrapeSubFilter, loadPipelineView, pipelineSortBy, pipelineSortDir, pipelinePageSize, pipelineActiveLetters],
  )

  const onPipelineScrapeSubFilterChange = useCallback(
    (sub: ScrapeSubFilter) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      setPipelineScrapeSubFilter(sub)
      setPipelineSelectedIds([])
      setPipelineOffset(0)
      const sf = scrapeSubToFilter(sub)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, 0, [...pipelineActiveLetters])
    },
    [activeView, pipelineDecisionFilter, loadPipelineView, pipelineSortBy, pipelineSortDir, pipelinePageSize, pipelineActiveLetters],
  )

  const onPipelinePagePrev = useCallback(() => {
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    const newOffset = Math.max(0, pipelineOffset - pipelinePageSize)
    setPipelineOffset(newOffset)
    const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
    void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, newOffset, [...pipelineActiveLetters])
  }, [activeView, pipelineDecisionFilter, pipelineOffset, pipelinePageSize, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, loadPipelineView, pipelineActiveLetters])

  const onPipelinePageNext = useCallback(() => {
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    const newOffset = pipelineOffset + pipelinePageSize
    setPipelineOffset(newOffset)
    const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
    void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, newOffset, [...pipelineActiveLetters])
  }, [activeView, pipelineDecisionFilter, pipelineOffset, pipelinePageSize, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, loadPipelineView, pipelineActiveLetters])

  const onPipelinePageSizeChange = useCallback(
    (size: number) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      setPipelinePageSize(size)
      setPipelineOffset(0)
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, size, 0, [...pipelineActiveLetters])
    },
    [activeView, pipelineDecisionFilter, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, loadPipelineView, pipelineActiveLetters],
  )

  const onPipelineSort = useCallback(
    (field: string) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      const newDir: 'asc' | 'desc' =
        pipelineSortBy === field
          ? pipelineSortDir === 'asc'
            ? 'desc'
            : 'asc'
          : SORT_DESC_FIRST.has(field)
            ? 'desc'
            : 'asc'
      setPipelineSortBy(field)
      setPipelineSortDir(newDir)
      setPipelineOffset(0)
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, field, newDir, pipelinePageSize, 0, [...pipelineActiveLetters])
    },
    [activeView, pipelineDecisionFilter, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, pipelinePageSize, loadPipelineView, pipelineActiveLetters],
  )

  const scrapeSelectedAsync = useCallback(async () => {
    if (!pipelineSelectedIds.length) return
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    setError('')
    setNotice('')
    setIsPipelineScraping(true)
    try {
      const result = await scrapeSelectedCompanies(selectedCampaignId, pipelineSelectedIds, {
        scrapeRules: selectedScrapePrompt?.scrape_rules_structured ?? undefined,
      })
      setNotice(`Queued ${result.queued_count} scrape job${result.queued_count === 1 ? '' : 's'}.`)
      setPipelineSelectedIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsPipelineScraping(false)
    }
  }, [pipelineSelectedIds, selectedCampaignId, selectedScrapePrompt, setError, setNotice])

  const onPipelineScrapeSelected = useCallback(() => {
    void scrapeSelectedAsync()
  }, [scrapeSelectedAsync])

  const analyzeSelectedAsync = useCallback(async () => {
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    if (!pipelineSelectedIds.length || !selectedPrompt?.enabled) {
      setError('Select an enabled prompt before running analysis.')
      return
    }
    setError('')
    setNotice('')
    setIsPipelineAnalyzing(true)
    try {
      const result = await createRuns({
        campaign_id: selectedCampaignId,
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
  }, [pipelineSelectedIds, selectedCampaignId, selectedPrompt, setError, setNotice])

  const onPipelineAnalyzeSelected = useCallback(() => {
    void analyzeSelectedAsync()
  }, [analyzeSelectedAsync])

  const fetchContactsAsync = useCallback(
    async (source: 'snov' | 'apollo' | 'both') => {
      if (!pipelineSelectedIds.length) return
      if (!selectedCampaignId) {
        setError('Select a campaign first.')
        return
      }
      setError('')
      setNotice('')
      setIsPipelineFetching(true)
      try {
        const result = await fetchContactsSelected(selectedCampaignId, pipelineSelectedIds, source)
        setNotice(
          source === 'both'
            ? `Queued ${result.queued_count} compan${result.queued_count === 1 ? 'y' : 'ies'} using sequential both-provider flow (Snov first, Apollo follow-up).`
            : `Queued contact fetch for ${result.queued_count} compan${result.queued_count === 1 ? 'y' : 'ies'} via ${source}.`,
        )
        setPipelineSelectedIds([])
      } catch (err) {
        setError(parseApiError(err))
      } finally {
        setIsPipelineFetching(false)
      }
    },
    [pipelineSelectedIds, selectedCampaignId, setError, setNotice],
  )

  const onPipelineFetchContacts = useCallback(
    (source: 'snov' | 'apollo' | 'both') => {
      void fetchContactsAsync(source)
    },
    [fetchContactsAsync],
  )

  const onPipelineSetManualLabel = useCallback(async (company: CompanyListItem, label: ManualLabel | null) => {
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return

    setError('')
    setNotice('')
    setPipelineManualLabelActionState((prev) => ({ ...prev, [company.id]: 'Saving…' }))

    try {
      await upsertCompanyFeedback(company.id, {
        thumbs: company.feedback_thumbs ?? null,
        comment: company.feedback_comment ?? null,
        manual_label: label,
      })
      setPipelineSelectedIds((prev) => prev.filter((id) => id !== company.id))
      const scrapeFilter = scrapeSubToFilter(pipelineScrapeSubFilter)
      await loadPipelineView(
        query.stageFilter,
        query.decisionFilter,
        scrapeFilter,
        pipelineSortBy,
        pipelineSortDir,
        pipelinePageSize,
        pipelineOffset,
        [...pipelineActiveLetters],
      )
      setNotice(
        label == null
          ? `Cleared manual label for ${company.domain}.`
          : `Saved manual label "${label}" for ${company.domain}.`,
      )
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setPipelineManualLabelActionState((prev) => {
        const next = { ...prev }
        delete next[company.id]
        return next
      })
    }
  }, [
    activeView,
    loadPipelineView,
    pipelineDecisionFilter,
    pipelineOffset,
    pipelinePageSize,
    pipelineScrapeSubFilter,
    pipelineSortBy,
    pipelineSortDir,
    pipelineActiveLetters,
    setError,
    setNotice,
  ])

  const refreshPipelineView = useCallback((options?: { background?: boolean }) => {
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query !== null) {
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(
        query.stageFilter,
        query.decisionFilter,
        sf,
        pipelineSortBy,
        pipelineSortDir,
        pipelinePageSize,
        pipelineOffset,
        [...pipelineActiveLetters],
        options,
      )
    } else if (activeView === 'full-pipeline') {
      void loadFullPipelineView(
        fullPipelineActiveLetter,
        fullPipelinePageSize,
        fullPipelineOffset,
        fullPipelineSortBy,
        fullPipelineSortDir,
        options,
      )
    } else if (activeView === 's4-validation') {
      void loadS4View(
        s4SortBy,
        s4SortDir,
        s4VerifFilter,
        s4PageSize,
        s4Offset,
        [...s4ActiveLetters],
        options,
      )
    }
  }, [
    activeView,
    pipelineDecisionFilter,
    pipelineScrapeSubFilter,
    pipelineOffset,
    pipelinePageSize,
    pipelineActiveLetters,
    loadPipelineView,
    loadFullPipelineView,
    fullPipelineActiveLetter,
    fullPipelineOffset,
    fullPipelinePageSize,
    fullPipelineSortBy,
    fullPipelineSortDir,
    loadS4View,
    pipelineSortBy,
    pipelineSortDir,
    s4SortBy,
    s4SortDir,
    s4VerifFilter,
    s4PageSize,
    s4Offset,
    s4ActiveLetters,
  ])

  useEffect(() => {
    if (skipNextPipelineLetterReloadRef.current) {
      skipNextPipelineLetterReloadRef.current = false
      return
    }
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    setPipelineSelectedIds([])
    setPipelineOffset(0)
    const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
    void loadPipelineView(
      query.stageFilter,
      query.decisionFilter,
      sf,
      pipelineSortBy,
      pipelineSortDir,
      pipelinePageSize,
      0,
      [...pipelineActiveLetters],
    )
  // Only react to letter changes (and view switches into S1-S3).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, pipelineActiveLetters])

  useEffect(() => {
    if (skipNextS4LetterReloadRef.current) {
      skipNextS4LetterReloadRef.current = false
      return
    }
    if (activeView !== 's4-validation') return
    setS4SelectedContactIds([])
    setS4Offset(0)
    void loadS4View(s4SortBy, s4SortDir, s4VerifFilter, s4PageSize, 0, [...s4ActiveLetters])
  }, [activeView, s4ActiveLetters, loadS4View])

  // ── Full pipeline handlers ─────────────────────────────────────────────────

  const onFullPipelineLetterChange = useCallback((letter: string | null) => {
    setFullPipelineActiveLetter(letter)
    setFullPipelineSelectedIds([])
    setFullPipelineOffset(0)
    void loadFullPipelineView(letter, fullPipelinePageSize, 0, fullPipelineSortBy, fullPipelineSortDir)
  }, [fullPipelinePageSize, fullPipelineSortBy, fullPipelineSortDir, loadFullPipelineView])

  const onFullPipelineToggleRow = useCallback((id: string) => {
    setFullPipelineSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [])

  const onFullPipelineToggleAll = useCallback((ids: string[]) => {
    setFullPipelineSelectedIds(ids)
  }, [])

  const onFullPipelineClearSelection = useCallback(() => setFullPipelineSelectedIds([]), [])

  const onFullPipelinePagePrev = useCallback(() => {
    const nextOffset = Math.max(0, fullPipelineOffset - fullPipelinePageSize)
    setFullPipelineOffset(nextOffset)
    void loadFullPipelineView(
      fullPipelineActiveLetter,
      fullPipelinePageSize,
      nextOffset,
      fullPipelineSortBy,
      fullPipelineSortDir,
    )
  }, [
    fullPipelineActiveLetter,
    fullPipelineOffset,
    fullPipelinePageSize,
    fullPipelineSortBy,
    fullPipelineSortDir,
    loadFullPipelineView,
  ])

  const onFullPipelinePageNext = useCallback(() => {
    const nextOffset = fullPipelineOffset + fullPipelinePageSize
    setFullPipelineOffset(nextOffset)
    void loadFullPipelineView(
      fullPipelineActiveLetter,
      fullPipelinePageSize,
      nextOffset,
      fullPipelineSortBy,
      fullPipelineSortDir,
    )
  }, [
    fullPipelineActiveLetter,
    fullPipelineOffset,
    fullPipelinePageSize,
    fullPipelineSortBy,
    fullPipelineSortDir,
    loadFullPipelineView,
  ])

  const onFullPipelinePageSizeChange = useCallback((size: number) => {
    setFullPipelinePageSize(size)
    setFullPipelineOffset(0)
    void loadFullPipelineView(fullPipelineActiveLetter, size, 0, fullPipelineSortBy, fullPipelineSortDir)
  }, [fullPipelineActiveLetter, fullPipelineSortBy, fullPipelineSortDir, loadFullPipelineView])

  const onFullPipelineSort = useCallback(
    (field: string) => {
      const newDir: 'asc' | 'desc' =
        fullPipelineSortBy === field
          ? fullPipelineSortDir === 'asc'
            ? 'desc'
            : 'asc'
          : SORT_DESC_FIRST.has(field)
            ? 'desc'
            : 'asc'
      setFullPipelineSortBy(field)
      setFullPipelineSortDir(newDir)
      setFullPipelineOffset(0)
      void loadFullPipelineView(fullPipelineActiveLetter, fullPipelinePageSize, 0, field, newDir)
    },
    [
      fullPipelineActiveLetter,
      fullPipelinePageSize,
      fullPipelineSortBy,
      fullPipelineSortDir,
      loadFullPipelineView,
    ],
  )

  const fullPipelineScrapeAsync = useCallback(async () => {
    if (!fullPipelineSelectedIds.length) return
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    if (!selectedPrompt?.enabled) {
      setError('Select an enabled decision prompt before starting pipeline.')
      return
    }
    setError('')
    setNotice('')
    setIsFullPipelineScraping(true)
    try {
      const result = await startPipelineRun({
        campaign_id: selectedCampaignId,
        company_ids: fullPipelineSelectedIds,
        scrape_rules_snapshot: selectedScrapePrompt?.scrape_rules_structured ?? undefined,
        analysis_prompt_snapshot: {
          prompt_id: selectedPrompt.id,
          prompt_text: selectedPrompt.prompt_text,
        },
      })
      setNotice(
        `Pipeline started for ${result.requested_count} selected compan${result.requested_count === 1 ? 'y' : 'ies'}.`,
      )
      setFullPipelineSelectedIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsFullPipelineScraping(false)
    }
  }, [fullPipelineSelectedIds, selectedCampaignId, selectedPrompt, selectedScrapePrompt, setError, setNotice])

  const onFullPipelineScrapeSelected = useCallback(() => {
    void fullPipelineScrapeAsync()
  }, [fullPipelineScrapeAsync])

  const FULL_PIPELINE_SELECT_BATCH = 500

  const fullPipelineSelectAllMatchingAsync = useCallback(
    async (statusFilter: FullPipelineStatusFilter, search: string) => {
      if (!selectedCampaignId) return
      setError('')
      setNotice('')
      setIsFullPipelineSelectingAllMatching(true)
      try {
        const letter = fullPipelineActiveLetter
        const q = search.trim()
        let ids: string[] = []

        if (statusFilter === 'all' && !q) {
          const result = await listCompanyIds(selectedCampaignId, 'all', 'all', 'all', letter)
          ids = result.ids.map((id) => String(id))
        } else {
          let offset = 0
          for (;;) {
            const page = await listCompanies(
              selectedCampaignId,
              FULL_PIPELINE_SELECT_BATCH,
              offset,
              'all',
              false,
              'all',
              'all',
              letter,
            )
            for (const c of page.items) {
              if (matchesFullPipelineFilters(c, statusFilter, search)) ids.push(c.id)
            }
            if (!page.has_more) break
            offset += FULL_PIPELINE_SELECT_BATCH
          }
        }

        setFullPipelineSelectedIds(ids)
        setNotice(
          ids.length > 0
            ? `Selected ${ids.length.toLocaleString()} compan${ids.length === 1 ? 'y' : 'ies'} matching filters.`
            : 'No companies match these filters for the current list scope.',
        )
      } catch (err) {
        setError(parseApiError(err))
      } finally {
        setIsFullPipelineSelectingAllMatching(false)
      }
    },
    [fullPipelineActiveLetter, selectedCampaignId, setError, setNotice],
  )

  const onFullPipelineSelectAllMatching = useCallback(
    (statusFilter: FullPipelineStatusFilter, search: string) => {
      void fullPipelineSelectAllMatchingAsync(statusFilter, search)
    },
    [fullPipelineSelectAllMatchingAsync],
  )

  const fullPipelineResumeCompanyAsync = useCallback(async (company: CompanyListItem) => {
    const setAction = (label: string) => setFullPipelineResumeState((prev) => ({ ...prev, [company.id]: label }))
    const resumeStage = getResumeStageForCompany(company)

    setError('')
    setNotice('')
    try {
      if (!selectedCampaignId) {
        setError('Select a campaign first.')
        return
      }
      if (resumeStage === 'S1') {
        setAction('Resuming S1…')
        const result = await scrapeSelectedCompanies(selectedCampaignId, [company.id], {
          scrapeRules: selectedScrapePrompt?.scrape_rules_structured ?? undefined,
        })
        setNotice(`Resumed S1 for ${company.domain}. Queued ${result.queued_count} scrape job(s).`)
        return
      }
      if (resumeStage === 'S2') {
        if (!selectedPrompt?.enabled) {
          setError('Select an enabled prompt before resuming AI stage.')
          return
        }
        setAction('Resuming S2…')
        const result = await createRuns({
          campaign_id: selectedCampaignId,
          prompt_id: selectedPrompt.id,
          scope: 'selected',
          company_ids: [company.id],
        })
        setNotice(`Resumed S2 for ${company.domain}. Queued ${result.queued_count} analysis job(s).`)
        return
      }
      if (resumeStage === 'S3') {
        setAction('Resuming S3…')
        const result = await fetchContactsSelected(selectedCampaignId, [company.id], 'both')
        setNotice(`Resumed S3 for ${company.domain}. Queued ${result.queued_count} contact fetch job(s).`)
        return
      }
      setNotice(`No failed stage to resume for ${company.domain}.`)
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setFullPipelineResumeState((prev) => {
        const next = { ...prev }
        delete next[company.id]
        return next
      })
    }
  }, [selectedCampaignId, selectedPrompt, selectedScrapePrompt, setError, setNotice])

  const onFullPipelineResumeCompany = useCallback((company: CompanyListItem) => {
    void fullPipelineResumeCompanyAsync(company)
  }, [fullPipelineResumeCompanyAsync])

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
    setS4SelectedContactIds(ids)
  }, [])

  const onS4ClearSelection = useCallback(() => setS4SelectedContactIds([]), [])

  const onS4VerifFilterChange = useCallback(
    (filter: S4VerifFilter) => {
      setS4VerifFilter(filter)
      setS4SelectedContactIds([])
      setS4Offset(0)
      void loadS4View(s4SortBy, s4SortDir, filter, s4PageSize, 0, [...s4ActiveLetters])
    },
    [loadS4View, s4SortBy, s4SortDir, s4PageSize, s4ActiveLetters],
  )

  const onS4PagePrev = useCallback(() => {
    const newOffset = Math.max(0, s4Offset - s4PageSize)
    setS4Offset(newOffset)
    void loadS4View(s4SortBy, s4SortDir, s4VerifFilter, s4PageSize, newOffset, [...s4ActiveLetters])
  }, [s4Offset, s4PageSize, s4SortBy, s4SortDir, s4VerifFilter, s4ActiveLetters, loadS4View])

  const onS4PageNext = useCallback(() => {
    const newOffset = s4Offset + s4PageSize
    setS4Offset(newOffset)
    void loadS4View(s4SortBy, s4SortDir, s4VerifFilter, s4PageSize, newOffset, [...s4ActiveLetters])
  }, [s4Offset, s4PageSize, s4SortBy, s4SortDir, s4VerifFilter, s4ActiveLetters, loadS4View])

  const onS4PageSizeChange = useCallback(
    (size: number) => {
      setS4PageSize(size)
      setS4Offset(0)
      void loadS4View(s4SortBy, s4SortDir, s4VerifFilter, size, 0, [...s4ActiveLetters])
    },
    [s4SortBy, s4SortDir, s4VerifFilter, s4ActiveLetters, loadS4View],
  )

  const onS4Sort = useCallback(
    (field: string) => {
      const newDir: 'asc' | 'desc' =
        s4SortBy === field
          ? s4SortDir === 'asc'
            ? 'desc'
            : 'asc'
          : SORT_DESC_FIRST.has(field)
            ? 'desc'
            : 'asc'
      setS4SortBy(field)
      setS4SortDir(newDir)
      setS4Offset(0)
      void loadS4View(field, newDir, s4VerifFilter, s4PageSize, 0, [...s4ActiveLetters])
    },
    [s4SortBy, s4SortDir, s4VerifFilter, s4PageSize, s4ActiveLetters, loadS4View],
  )

  const validateSelectedAsync = useCallback(async () => {
    if (!s4SelectedContactIds.length) return
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    setError('')
    setNotice('')
    setIsS4Validating(true)
    try {
      const result = await verifyContacts({ campaign_id: selectedCampaignId, contact_ids: s4SelectedContactIds })
      setNotice(result.message)
      setS4SelectedContactIds([])
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsS4Validating(false)
    }
  }, [s4SelectedContactIds, selectedCampaignId, setError, setNotice])

  const onS4ValidateSelected = useCallback(() => {
    void validateSelectedAsync()
  }, [validateSelectedAsync])

  return {
    fullPipelineCompanies,
    fullPipelineLetterCounts,
    fullPipelineActiveLetter,
    fullPipelineSelectedIds,
    fullPipelineResumeState,
    fullPipelineOffset,
    fullPipelinePageSize,
    isFullPipelineLoading,
    isFullPipelineScraping,
    isFullPipelineSelectingAllMatching,
    onFullPipelineLetterChange,
    onFullPipelineToggleRow,
    onFullPipelineToggleAll,
    onFullPipelineClearSelection,
    onFullPipelineScrapeSelected,
    onFullPipelineResumeCompany,
    onFullPipelinePagePrev,
    onFullPipelinePageNext,
    onFullPipelinePageSizeChange,
    onFullPipelineSelectAllMatching,
    fullPipelineSortBy,
    fullPipelineSortDir,
    onFullPipelineSort,
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
    pipelineOffset,
    pipelinePageSize,
    pipelineSortBy,
    pipelineSortDir,
    onPipelineDecisionFilterChange,
    onPipelineScrapeSubFilterChange,
    onPipelinePagePrev,
    onPipelinePageNext,
    onPipelinePageSizeChange,
    onPipelineSort,
    s4Contacts,
    s4LetterCounts,
    s4ActiveLetters,
    s4SelectedContactIds,
    s4VerifFilter,
    s4Offset,
    s4PageSize,
    isS4Loading,
    isS4Validating,
    s4SortBy,
    s4SortDir,
    onS4Sort,
    onS4VerifFilterChange,
    onS4PagePrev,
    onS4PageNext,
    onS4PageSizeChange,
    onPipelineToggleLetter,
    onPipelineClearLetters,
    onPipelineToggleRow,
    onPipelineToggleAll,
    onPipelineSelectAllMatching,
    onPipelineClearSelection,
    onPipelineScrapeSelected,
    onPipelineAnalyzeSelected,
    onPipelineFetchContacts,
    pipelineManualLabelActionState,
    onPipelineSetManualLabel,
    refreshPipelineView,
    onS4ToggleLetter,
    onS4ClearLetters,
    onS4ToggleContact,
    onS4ToggleAll,
    onS4ClearSelection,
    onS4ValidateSelected,
  }
}
