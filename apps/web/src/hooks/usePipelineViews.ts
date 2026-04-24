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
  getDiscoveredContactCounts,
  getLetterCounts,
  listCompanies,
  listCompanyIds,
  listContacts,
  listDiscoveredContacts,
  revealDiscoveredContactEmails,
  scrapeSelectedCompanies,
  startPipelineRun,
  upsertCompanyFeedback,
  verifyContacts,
} from '../lib/api'
import type { DiscoveredContactListResponse, DiscoveredContactCountsResponse } from '../lib/types'
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
  fullPipelineStatusFilter: FullPipelineStatusFilter
  fullPipelineSearch: string
  isFullPipelineLoading: boolean
  isFullPipelineScraping: boolean
  isFullPipelineSelectingAllMatching: boolean
  onFullPipelineStatusFilterChange: (filter: FullPipelineStatusFilter) => void
  onFullPipelineSearchChange: (value: string) => void
  onFullPipelineLetterChange: (l: string | null) => void
  onFullPipelineToggleRow: (id: string) => void
  onFullPipelineToggleAll: (ids: string[]) => void
  onFullPipelineClearSelection: () => void
  onFullPipelineScrapeSelected: () => void
  onFullPipelineResumeCompany: (company: CompanyListItem) => void
  onFullPipelinePagePrev: () => void
  onFullPipelinePageNext: () => void
  onFullPipelinePageSizeChange: (size: number) => void
  onFullPipelineSelectAllMatching: () => void
  fullPipelineSortBy: string
  fullPipelineSortDir: 'asc' | 'desc'
  onFullPipelineSort: (field: string) => void
  // S1–S3 company list
  pipelineCompanies: CompanyList | null
  pipelineLetterCounts: Record<string, number>
  pipelineActiveLetters: Set<string>
  pipelineSelectedIds: string[]
  pipelineSearch: string
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
  onPipelineSearchChange: (value: string) => void
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
  onPipelineFetchContacts: () => void
  pipelineManualLabelActionState: Record<string, string>
  onPipelineSetManualLabel: (company: CompanyListItem, label: ManualLabel | null) => void
  cancelStaleSelectAllRequests: () => void
  refreshPipelineView: (options?: { background?: boolean }) => void
  // S4 handlers
  onS4ToggleLetter: (l: string) => void
  onS4ClearLetters: () => void
  onS4ToggleContact: (id: string) => void
  onS4ToggleAll: (ids: string[]) => void
  onS4ClearSelection: () => void
  onS4ValidateSelected: () => void
  // S4 reveal state
  s4DiscoveredContacts: DiscoveredContactListResponse | null
  s4DiscoveredCounts: DiscoveredContactCountsResponse | null
  s4DiscoveredSelectedIds: string[]
  s4MatchFilter: 'all' | 'matched' | 'unmatched'
  s4RevealOffset: number
  s4RevealPageSize: number
  isS4RevealLoading: boolean
  isS4Revealing: boolean
  onS4ToggleDiscovered: (id: string) => void
  onS4ToggleAllDiscovered: (ids: string[]) => void
  onS4ClearDiscoveredSelection: () => void
  onS4MatchFilterChange: (f: 'all' | 'matched' | 'unmatched') => void
  onS4RevealPagePrev: () => void
  onS4RevealPageNext: () => void
  onS4RevealSelected: () => void
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
  const [pipelineSearch, setPipelineSearch] = useState('')
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
  const [fullPipelineStatusFilter, setFullPipelineStatusFilter] = useState<FullPipelineStatusFilter>('all')
  const [fullPipelineSearch, setFullPipelineSearch] = useState('')
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
  // S4 reveal state
  const [s4DiscoveredContacts, setS4DiscoveredContacts] = useState<DiscoveredContactListResponse | null>(null)
  const [s4DiscoveredCounts, setS4DiscoveredCounts] = useState<DiscoveredContactCountsResponse | null>(null)
  const [s4DiscoveredSelectedIds, setS4DiscoveredSelectedIds] = useState<string[]>([])
  const [s4MatchFilter, setS4MatchFilter] = useState<'all' | 'matched' | 'unmatched'>('all')
  const [s4RevealOffset, setS4RevealOffset] = useState(0)
  const s4RevealPageSize = 50
  const [isS4RevealLoading, setIsS4RevealLoading] = useState(false)
  const [isS4Revealing, setIsS4Revealing] = useState(false)
  const pipelineRequestRef = useRef(0)
  const pipelineForegroundRequestRef = useRef(0)
  const pipelineSelectAllRequestRef = useRef(0)
  const pipelineSelectAllForegroundRequestRef = useRef(0)
  const s4RequestRef = useRef(0)
  const s4ForegroundRequestRef = useRef(0)
  const fullPipelineRequestRef = useRef(0)
  const fullPipelineForegroundRequestRef = useRef(0)
  const fullPipelineSelectAllRequestRef = useRef(0)
  const fullPipelineSelectAllForegroundRequestRef = useRef(0)
  const skipNextPipelineLetterReloadRef = useRef(false)
  const skipNextS4LetterReloadRef = useRef(false)

  // ── Load functions ─────────────────────────────────────────────────────────

  const invalidatePipelineSelectAllRequest = useCallback(() => {
    pipelineSelectAllRequestRef.current += 1
    pipelineSelectAllForegroundRequestRef.current = pipelineSelectAllRequestRef.current
    setIsPipelineSelectingAll(false)
  }, [])

  const invalidateFullPipelineSelectAllRequest = useCallback(() => {
    fullPipelineSelectAllRequestRef.current += 1
    fullPipelineSelectAllForegroundRequestRef.current = fullPipelineSelectAllRequestRef.current
    setIsFullPipelineSelectingAllMatching(false)
  }, [])

  const cancelStaleSelectAllRequests = useCallback(() => {
    invalidatePipelineSelectAllRequest()
    invalidateFullPipelineSelectAllRequest()
  }, [invalidateFullPipelineSelectAllRequest, invalidatePipelineSelectAllRequest])

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
      search = '',
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
          listCompanies(selectedCampaignId, pageSize, offset, decisionFilter, true, scrapeFilter, stageFilter, null, sortBy, sortDir, undefined, letters, 'all', search),
          getLetterCounts(selectedCampaignId, decisionFilter, scrapeFilter, stageFilter, undefined, 'all', search),
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

  const loadS4RevealView = useCallback(async () => {
    if (!requestsEnabled || !selectedCampaignId) {
      setS4DiscoveredContacts(null)
      setS4DiscoveredCounts(null)
      setIsS4RevealLoading(false)
      return
    }
    setIsS4RevealLoading(true)
    try {
      const matchedOnly = s4MatchFilter === 'matched' ? true : undefined
      const [contacts, counts] = await Promise.all([
        listDiscoveredContacts({ campaignId: selectedCampaignId, matchedOnly, limit: s4RevealPageSize, offset: s4RevealOffset }),
        getDiscoveredContactCounts(selectedCampaignId),
      ])
      setS4DiscoveredContacts(contacts)
      setS4DiscoveredCounts(counts)
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsS4RevealLoading(false)
    }
  }, [requestsEnabled, selectedCampaignId, s4MatchFilter, s4RevealOffset, s4RevealPageSize, setError])

  const loadFullPipelineView = useCallback(
    async (
      letter: string | null,
      pageSize: number,
      offset: number,
      sortBy: string,
      sortDir: 'asc' | 'desc',
      statusFilter: FullPipelineStatusFilter = 'all',
      search = '',
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
          listCompanies(selectedCampaignId, pageSize, offset, 'all', true, 'all', 'all', letter, sortBy, sortDir, undefined, undefined, statusFilter, search),
          getLetterCounts(selectedCampaignId, 'all', 'all', 'all', undefined, statusFilter, search),
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
    cancelStaleSelectAllRequests()
    const defaultDecisionFilter: DecisionFilter = activeView === 's3-contacts' ? 'labeled' : 'all'
    const query = getPipelineCompanyQuery(activeView, defaultDecisionFilter)
    if (query !== null) {
      const defaultScrapeSubFilter = getDefaultPipelineScrapeSubFilter(activeView)
      const defaultScrapeFilter = scrapeSubToFilter(defaultScrapeSubFilter)
      setPipelineSelectedIds([])
      skipNextPipelineLetterReloadRef.current = true
      setPipelineActiveLetters(new Set())
      setPipelineSearch('')
      setPipelineDecisionFilter(defaultDecisionFilter)
      setPipelineManualLabelActionState({})
      setPipelineScrapeSubFilter(defaultScrapeSubFilter)
      setPipelineOffset(0)
      setPipelinePageSize(DEFAULT_PAGE_SIZE)
      setPipelineSortBy('last_activity')
      setPipelineSortDir('desc')
      void loadPipelineView(query.stageFilter, query.decisionFilter, defaultScrapeFilter, 'last_activity', 'desc', DEFAULT_PAGE_SIZE, 0, [], '')
    } else if (activeView === 'full-pipeline') {
      setFullPipelineSelectedIds([])
      setFullPipelineActiveLetter(null)
      setFullPipelineOffset(0)
      setFullPipelinePageSize(DEFAULT_PAGE_SIZE)
      setFullPipelineStatusFilter('all')
      setFullPipelineSearch('')
      setFullPipelineSortBy('last_activity')
      setFullPipelineSortDir('desc')
      void loadFullPipelineView(null, DEFAULT_PAGE_SIZE, 0, 'last_activity', 'desc', 'all', '')
    } else if (activeView === 's4-reveal') {
      setS4DiscoveredSelectedIds([])
      setS4MatchFilter('all')
      setS4RevealOffset(0)
      void loadS4RevealView()
    } else if (activeView === 's5-validation') {
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
  }, [activeView, cancelStaleSelectAllRequests, loadPipelineView, loadFullPipelineView, loadS4RevealView, loadS4View])

  // ── S1–S3 handlers ─────────────────────────────────────────────────────────

  const onPipelineToggleLetter = useCallback((letter: string) => {
    invalidatePipelineSelectAllRequest()
    setPipelineActiveLetters((prev) => {
      const next = new Set(prev)
      if (next.has(letter)) next.delete(letter)
      else next.add(letter)
      return next
    })
    setPipelineSelectedIds([])
  }, [invalidatePipelineSelectAllRequest])

  const onPipelineClearLetters = useCallback(() => {
    invalidatePipelineSelectAllRequest()
    setPipelineActiveLetters(new Set())
    setPipelineSelectedIds([])
  }, [invalidatePipelineSelectAllRequest])

  const onPipelineToggleRow = useCallback((id: string) => {
    invalidatePipelineSelectAllRequest()
    setPipelineSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [invalidatePipelineSelectAllRequest])

  const onPipelineToggleAll = useCallback((ids: string[]) => {
    invalidatePipelineSelectAllRequest()
    setPipelineSelectedIds(ids)
  }, [invalidatePipelineSelectAllRequest])

  const selectAllMatchingAsync = useCallback(async () => {
    if (!selectedCampaignId) return
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    const requestId = pipelineSelectAllRequestRef.current + 1
    pipelineSelectAllRequestRef.current = requestId
    pipelineSelectAllForegroundRequestRef.current = requestId
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
        'all',
        pipelineSearch,
      )
      if (pipelineSelectAllRequestRef.current !== requestId) return
      setPipelineSelectedIds(result.ids.map((id) => String(id)))
    } catch (err) {
      if (pipelineSelectAllRequestRef.current !== requestId) return
      setError(parseApiError(err))
    } finally {
      if (pipelineSelectAllForegroundRequestRef.current === requestId) {
        setIsPipelineSelectingAll(false)
      }
    }
  }, [activeView, pipelineActiveLetters, pipelineDecisionFilter, pipelineScrapeSubFilter, pipelineSearch, selectedCampaignId, setError])

  const onPipelineSelectAllMatching = useCallback(() => {
    void selectAllMatchingAsync()
  }, [selectAllMatchingAsync])

  const onPipelineClearSelection = useCallback(() => {
    invalidatePipelineSelectAllRequest()
    setPipelineSelectedIds([])
  }, [invalidatePipelineSelectAllRequest])

  const onPipelineSearchChange = useCallback(
    (search: string) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      invalidatePipelineSelectAllRequest()
      setPipelineSearch(search)
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
        search,
      )
    },
    [
      activeView,
      pipelineDecisionFilter,
      invalidatePipelineSelectAllRequest,
      pipelineScrapeSubFilter,
      pipelineSearch,
      pipelineSortBy,
      pipelineSortDir,
      pipelinePageSize,
      pipelineActiveLetters,
      loadPipelineView,
    ],
  )

  const onPipelineDecisionFilterChange = useCallback(
    (decisionFilter: DecisionFilter) => {
      const query = getPipelineCompanyQuery(activeView, decisionFilter)
      if (query === null) return
      invalidatePipelineSelectAllRequest()
      setPipelineDecisionFilter(decisionFilter)
      setPipelineSelectedIds([])
      setPipelineOffset(0)
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, 0, [...pipelineActiveLetters], pipelineSearch)
    },
    [activeView, invalidatePipelineSelectAllRequest, pipelineScrapeSubFilter, pipelineSearch, loadPipelineView, pipelineSortBy, pipelineSortDir, pipelinePageSize, pipelineActiveLetters],
  )

  const onPipelineScrapeSubFilterChange = useCallback(
    (sub: ScrapeSubFilter) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      invalidatePipelineSelectAllRequest()
      setPipelineScrapeSubFilter(sub)
      setPipelineSelectedIds([])
      setPipelineOffset(0)
      const sf = scrapeSubToFilter(sub)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, 0, [...pipelineActiveLetters], pipelineSearch)
    },
    [activeView, invalidatePipelineSelectAllRequest, pipelineDecisionFilter, pipelineSearch, loadPipelineView, pipelineSortBy, pipelineSortDir, pipelinePageSize, pipelineActiveLetters],
  )

  const onPipelinePagePrev = useCallback(() => {
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    const newOffset = Math.max(0, pipelineOffset - pipelinePageSize)
    setPipelineOffset(newOffset)
    const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
    void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, newOffset, [...pipelineActiveLetters], pipelineSearch)
  }, [activeView, pipelineDecisionFilter, pipelineOffset, pipelinePageSize, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, loadPipelineView, pipelineActiveLetters, pipelineSearch])

  const onPipelinePageNext = useCallback(() => {
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return
    const newOffset = pipelineOffset + pipelinePageSize
    setPipelineOffset(newOffset)
    const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
    void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, pipelinePageSize, newOffset, [...pipelineActiveLetters], pipelineSearch)
  }, [activeView, pipelineDecisionFilter, pipelineOffset, pipelinePageSize, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, loadPipelineView, pipelineActiveLetters, pipelineSearch])

  const onPipelinePageSizeChange = useCallback(
    (size: number) => {
      const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
      if (query === null) return
      setPipelinePageSize(size)
      setPipelineOffset(0)
      const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, pipelineSortBy, pipelineSortDir, size, 0, [...pipelineActiveLetters], pipelineSearch)
    },
    [activeView, pipelineDecisionFilter, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, loadPipelineView, pipelineActiveLetters, pipelineSearch],
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
      void loadPipelineView(query.stageFilter, query.decisionFilter, sf, field, newDir, pipelinePageSize, 0, [...pipelineActiveLetters], pipelineSearch)
    },
    [activeView, pipelineDecisionFilter, pipelineScrapeSubFilter, pipelineSortBy, pipelineSortDir, pipelinePageSize, loadPipelineView, pipelineActiveLetters, pipelineSearch],
  )

  const scrapeSelectedAsync = useCallback(async () => {
    if (!pipelineSelectedIds.length) return
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    invalidatePipelineSelectAllRequest()
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
  }, [invalidatePipelineSelectAllRequest, pipelineSelectedIds, selectedCampaignId, selectedScrapePrompt, setError, setNotice])

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
    invalidatePipelineSelectAllRequest()
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
  }, [invalidatePipelineSelectAllRequest, pipelineSelectedIds, selectedCampaignId, selectedPrompt, setError, setNotice])

  const onPipelineAnalyzeSelected = useCallback(() => {
    void analyzeSelectedAsync()
  }, [analyzeSelectedAsync])

  const fetchContactsAsync = useCallback(
    async () => {
      if (!pipelineSelectedIds.length) return
      if (!selectedCampaignId) {
        setError('Select a campaign first.')
        return
      }
      invalidatePipelineSelectAllRequest()
      setError('')
      setNotice('')
      setIsPipelineFetching(true)
      try {
        const result = await fetchContactsSelected(selectedCampaignId, pipelineSelectedIds)
        setNotice(
          `Queued contact fetch for ${result.queued_count} compan${result.queued_count === 1 ? 'y' : 'ies'}.`,
        )
        setPipelineSelectedIds([])
      } catch (err) {
        setError(parseApiError(err))
      } finally {
        setIsPipelineFetching(false)
      }
    },
    [invalidatePipelineSelectAllRequest, pipelineSelectedIds, selectedCampaignId, setError, setNotice],
  )

  const onPipelineFetchContacts = useCallback(
    () => {
      void fetchContactsAsync()
    },
    [fetchContactsAsync],
  )

  const onPipelineSetManualLabel = useCallback(async (company: CompanyListItem, label: ManualLabel | null) => {
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (query === null) return

    invalidatePipelineSelectAllRequest()
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
        pipelineSearch,
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
    invalidatePipelineSelectAllRequest,
    loadPipelineView,
    pipelineDecisionFilter,
    pipelineOffset,
    pipelinePageSize,
    pipelineScrapeSubFilter,
    pipelineSortBy,
    pipelineSortDir,
    pipelineActiveLetters,
    pipelineSearch,
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
        pipelineSearch,
        options,
      )
    } else if (activeView === 'full-pipeline') {
      void loadFullPipelineView(
        fullPipelineActiveLetter,
        fullPipelinePageSize,
        fullPipelineOffset,
        fullPipelineSortBy,
        fullPipelineSortDir,
        fullPipelineStatusFilter,
        fullPipelineSearch,
        options,
      )
    } else if (activeView === 's5-validation') {
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
    fullPipelineStatusFilter,
    fullPipelineSearch,
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
      pipelineSearch,
    )
  // Only react to letter changes (and view switches into S1-S3).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, pipelineActiveLetters])

  useEffect(() => {
    if (skipNextS4LetterReloadRef.current) {
      skipNextS4LetterReloadRef.current = false
      return
    }
    if (activeView !== 's5-validation') return
    setS4SelectedContactIds([])
    setS4Offset(0)
    void loadS4View(s4SortBy, s4SortDir, s4VerifFilter, s4PageSize, 0, [...s4ActiveLetters])
  }, [activeView, s4ActiveLetters, loadS4View])

  // ── Full pipeline handlers ─────────────────────────────────────────────────

  const onFullPipelineStatusFilterChange = useCallback((statusFilter: FullPipelineStatusFilter) => {
    invalidateFullPipelineSelectAllRequest()
    setFullPipelineStatusFilter(statusFilter)
    setFullPipelineSelectedIds([])
    setFullPipelineOffset(0)
    void loadFullPipelineView(
      fullPipelineActiveLetter,
      fullPipelinePageSize,
      0,
      fullPipelineSortBy,
      fullPipelineSortDir,
      statusFilter,
      fullPipelineSearch,
    )
  }, [
    fullPipelineActiveLetter,
    fullPipelinePageSize,
    invalidateFullPipelineSelectAllRequest,
    fullPipelineSortBy,
    fullPipelineSortDir,
    fullPipelineSearch,
    loadFullPipelineView,
  ])

  const onFullPipelineSearchChange = useCallback((search: string) => {
    invalidateFullPipelineSelectAllRequest()
    setFullPipelineSearch(search)
    setFullPipelineSelectedIds([])
    setFullPipelineOffset(0)
    void loadFullPipelineView(
      fullPipelineActiveLetter,
      fullPipelinePageSize,
      0,
      fullPipelineSortBy,
      fullPipelineSortDir,
      fullPipelineStatusFilter,
      search,
    )
  }, [
    fullPipelineActiveLetter,
    fullPipelinePageSize,
    invalidateFullPipelineSelectAllRequest,
    fullPipelineSortBy,
    fullPipelineSortDir,
    fullPipelineStatusFilter,
    loadFullPipelineView,
  ])

  const onFullPipelineLetterChange = useCallback((letter: string | null) => {
    invalidateFullPipelineSelectAllRequest()
    setFullPipelineActiveLetter(letter)
    setFullPipelineSelectedIds([])
    setFullPipelineOffset(0)
    void loadFullPipelineView(
      letter,
      fullPipelinePageSize,
      0,
      fullPipelineSortBy,
      fullPipelineSortDir,
      fullPipelineStatusFilter,
      fullPipelineSearch,
    )
  }, [fullPipelinePageSize, invalidateFullPipelineSelectAllRequest, fullPipelineSortBy, fullPipelineSortDir, fullPipelineStatusFilter, fullPipelineSearch, loadFullPipelineView])

  const onFullPipelineToggleRow = useCallback((id: string) => {
    invalidateFullPipelineSelectAllRequest()
    setFullPipelineSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }, [invalidateFullPipelineSelectAllRequest])

  const onFullPipelineToggleAll = useCallback((ids: string[]) => {
    invalidateFullPipelineSelectAllRequest()
    setFullPipelineSelectedIds(ids)
  }, [invalidateFullPipelineSelectAllRequest])

  const onFullPipelineClearSelection = useCallback(() => {
    invalidateFullPipelineSelectAllRequest()
    setFullPipelineSelectedIds([])
  }, [invalidateFullPipelineSelectAllRequest])

  const onFullPipelinePagePrev = useCallback(() => {
    const nextOffset = Math.max(0, fullPipelineOffset - fullPipelinePageSize)
    setFullPipelineOffset(nextOffset)
    void loadFullPipelineView(
      fullPipelineActiveLetter,
      fullPipelinePageSize,
      nextOffset,
      fullPipelineSortBy,
      fullPipelineSortDir,
      fullPipelineStatusFilter,
      fullPipelineSearch,
    )
  }, [
    fullPipelineActiveLetter,
    fullPipelineOffset,
    fullPipelinePageSize,
    fullPipelineSortBy,
    fullPipelineSortDir,
    fullPipelineStatusFilter,
    fullPipelineSearch,
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
      fullPipelineStatusFilter,
      fullPipelineSearch,
    )
  }, [
    fullPipelineActiveLetter,
    fullPipelineOffset,
    fullPipelinePageSize,
    fullPipelineSortBy,
    fullPipelineSortDir,
    fullPipelineStatusFilter,
    fullPipelineSearch,
    loadFullPipelineView,
  ])

  const onFullPipelinePageSizeChange = useCallback((size: number) => {
    setFullPipelinePageSize(size)
    setFullPipelineOffset(0)
    void loadFullPipelineView(fullPipelineActiveLetter, size, 0, fullPipelineSortBy, fullPipelineSortDir, fullPipelineStatusFilter, fullPipelineSearch)
  }, [fullPipelineActiveLetter, fullPipelineSortBy, fullPipelineSortDir, fullPipelineStatusFilter, fullPipelineSearch, loadFullPipelineView])

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
      void loadFullPipelineView(fullPipelineActiveLetter, fullPipelinePageSize, 0, field, newDir, fullPipelineStatusFilter, fullPipelineSearch)
    },
    [
      fullPipelineActiveLetter,
      fullPipelinePageSize,
      fullPipelineSortBy,
      fullPipelineSortDir,
      fullPipelineStatusFilter,
      fullPipelineSearch,
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
    invalidateFullPipelineSelectAllRequest()
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
  }, [invalidateFullPipelineSelectAllRequest, fullPipelineSelectedIds, selectedCampaignId, selectedPrompt, selectedScrapePrompt, setError, setNotice])

  const onFullPipelineScrapeSelected = useCallback(() => {
    void fullPipelineScrapeAsync()
  }, [fullPipelineScrapeAsync])

  const fullPipelineSelectAllMatchingAsync = useCallback(
    async () => {
      if (!selectedCampaignId) return
      const requestId = fullPipelineSelectAllRequestRef.current + 1
      fullPipelineSelectAllRequestRef.current = requestId
      fullPipelineSelectAllForegroundRequestRef.current = requestId
      setError('')
      setNotice('')
      setIsFullPipelineSelectingAllMatching(true)
      try {
        const result = await listCompanyIds(
          selectedCampaignId,
          'all',
          'all',
          'all',
          fullPipelineActiveLetter,
          undefined,
          undefined,
          fullPipelineStatusFilter,
          fullPipelineSearch,
        )
        const ids = result.ids.map((id) => String(id))

        if (fullPipelineSelectAllRequestRef.current !== requestId) return
        setFullPipelineSelectedIds(ids)
        setNotice(
          ids.length > 0
            ? `Selected ${ids.length.toLocaleString()} compan${ids.length === 1 ? 'y' : 'ies'} matching filters.`
            : 'No companies match these filters for the current list scope.',
        )
      } catch (err) {
        if (fullPipelineSelectAllRequestRef.current !== requestId) return
        setError(parseApiError(err))
      } finally {
        if (fullPipelineSelectAllForegroundRequestRef.current === requestId) {
          setIsFullPipelineSelectingAllMatching(false)
        }
      }
    },
    [fullPipelineActiveLetter, fullPipelineSearch, fullPipelineStatusFilter, selectedCampaignId, setError, setNotice],
  )

  const onFullPipelineSelectAllMatching = useCallback(
    () => { void fullPipelineSelectAllMatchingAsync() },
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
        const result = await fetchContactsSelected(selectedCampaignId, [company.id])
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

  // S4 reveal handlers
  const onS4ToggleDiscovered = useCallback((id: string) => {
    setS4DiscoveredSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }, [])

  const onS4ToggleAllDiscovered = useCallback((ids: string[]) => {
    setS4DiscoveredSelectedIds((prev) => prev.length === ids.length ? [] : ids)
  }, [])

  const onS4ClearDiscoveredSelection = useCallback(() => {
    setS4DiscoveredSelectedIds([])
  }, [])

  const onS4MatchFilterChange = useCallback((f: 'all' | 'matched' | 'unmatched') => {
    setS4MatchFilter(f)
    setS4RevealOffset(0)
    setS4DiscoveredSelectedIds([])
  }, [])

  const onS4RevealPagePrev = useCallback(() => {
    setS4RevealOffset((prev) => Math.max(0, prev - s4RevealPageSize))
    setS4DiscoveredSelectedIds([])
  }, [s4RevealPageSize])

  const onS4RevealPageNext = useCallback(() => {
    setS4RevealOffset((prev) => prev + s4RevealPageSize)
    setS4DiscoveredSelectedIds([])
  }, [s4RevealPageSize])

  const onS4RevealSelected = useCallback(async () => {
    if (!selectedCampaignId || !s4DiscoveredSelectedIds.length) return
    setIsS4Revealing(true)
    setError('')
    setNotice('')
    try {
      const result = await revealDiscoveredContactEmails({ campaign_id: selectedCampaignId, discovered_contact_ids: s4DiscoveredSelectedIds })
      setNotice(`Queued email reveal for ${result.queued_count} contact${result.queued_count === 1 ? '' : 's'}.`)
      setS4DiscoveredSelectedIds([])
      void loadS4RevealView()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsS4Revealing(false)
    }
  }, [selectedCampaignId, s4DiscoveredSelectedIds, loadS4RevealView, setError, setNotice])

  return {
    fullPipelineCompanies,
    fullPipelineLetterCounts,
    fullPipelineActiveLetter,
    fullPipelineSelectedIds,
    fullPipelineResumeState,
    fullPipelineOffset,
    fullPipelinePageSize,
    fullPipelineStatusFilter,
    fullPipelineSearch,
    isFullPipelineLoading,
    isFullPipelineScraping,
    isFullPipelineSelectingAllMatching,
    onFullPipelineStatusFilterChange,
    onFullPipelineSearchChange,
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
    pipelineSearch,
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
    onPipelineSearchChange,
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
    cancelStaleSelectAllRequests,
    refreshPipelineView,
    onS4ToggleLetter,
    onS4ClearLetters,
    onS4ToggleContact,
    onS4ToggleAll,
    onS4ClearSelection,
    onS4ValidateSelected,
    s4DiscoveredContacts,
    s4DiscoveredCounts,
    s4DiscoveredSelectedIds,
    s4MatchFilter,
    s4RevealOffset,
    s4RevealPageSize,
    isS4RevealLoading,
    isS4Revealing,
    onS4ToggleDiscovered,
    onS4ToggleAllDiscovered,
    onS4ClearDiscoveredSelection,
    onS4MatchFilterChange,
    onS4RevealPagePrev,
    onS4RevealPageNext,
    onS4RevealSelected: () => { void onS4RevealSelected() },
  }
}
