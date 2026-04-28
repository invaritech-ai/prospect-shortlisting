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
  StatsResponse,
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
  listDiscoveredContactIds,
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
import {
  defaultCompanySortForStageView,
  defaultDiscoveredSort,
  defaultValidationContactSort,
} from '../lib/stageViewSort'

/** New sort on these fields defaults to descending (most recent first). */
const SORT_DESC_FIRST = new Set([
  'last_activity',
  'updated_at',
  'created_at',
  'last_seen_at',
  'title_match',
  'provider_has_email',
  'scrape_updated_at',
  'analysis_updated_at',
  'contact_fetch_updated_at',
])

export const PAGE_SIZE_OPTIONS = [25, 50, 100, 200] as const
const DEFAULT_PAGE_SIZE = 50

interface UsePipelineViewsResult {
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
  s4RevealLetterCounts: Record<string, number>
  s4RevealActiveLetters: Set<string>
  s4DiscoveredSelectedIds: string[]
  s4MatchFilter: 'all' | 'matched' | 'unmatched'
  s4RevealSearch: string
  s4RevealOffset: number
  s4RevealPageSize: number
  s4RevealSortBy: string
  s4RevealSortDir: 'asc' | 'desc'
  s4StaleEmailOnly: boolean
  isS4RevealLoading: boolean
  isS4Revealing: boolean
  isS4RevealSelectingAllMatching: boolean
  onS4ToggleDiscovered: (id: string) => void
  onS4ToggleAllDiscovered: (ids: string[]) => void
  onS4ClearDiscoveredSelection: () => void
  onS4MatchFilterChange: (f: 'all' | 'matched' | 'unmatched') => void
  onS4RevealSearchChange: (value: string) => void
  onS4RevealToggleLetter: (letter: string) => void
  onS4RevealClearLetters: () => void
  onS4RevealPagePrev: () => void
  onS4RevealPageNext: () => void
  onS4RevealPageSizeChange: (size: number) => void
  onS4RevealSort: (field: string) => void
  onS4RevealSelectAllMatching: () => void
  onS4RevealSelected: () => void
  onS4StaleEmailOnlyChange: (value: boolean) => void
}

export function usePipelineViews(
  activeView: ActiveView,
  selectedCampaignId: string | null,
  selectedPrompt: PromptRead | null,
  selectedScrapePrompt: ScrapePromptRead | null,
  requestsEnabled: boolean,
  setError: (e: string) => void,
  setNotice: (n: string) => void,
  stats: StatsResponse | null,
): UsePipelineViewsResult {
  const statsRef = useRef(stats)
  statsRef.current = stats
  const pipelineSortUserOverrideRef = useRef(false)
  const s4RevealSortUserOverrideRef = useRef(false)
  const s5ContactSortUserOverrideRef = useRef(false)
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
  const [s4RevealLetterCounts, setS4RevealLetterCounts] = useState<Record<string, number>>({})
  const [s4RevealActiveLetters, setS4RevealActiveLetters] = useState(new Set<string>())
  const [s4DiscoveredSelectedIds, setS4DiscoveredSelectedIds] = useState<string[]>([])
  const [s4MatchFilter, setS4MatchFilter] = useState<'all' | 'matched' | 'unmatched'>('all')
  const [s4RevealSearch, setS4RevealSearch] = useState('')
  const [s4RevealOffset, setS4RevealOffset] = useState(0)
  const [s4RevealPageSize, setS4RevealPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [s4RevealSortBy, setS4RevealSortBy] = useState('last_seen_at')
  const [s4RevealSortDir, setS4RevealSortDir] = useState<'asc' | 'desc'>('desc')
  const [s4StaleEmailOnly, setS4StaleEmailOnly] = useState(false)
  const [isS4RevealLoading, setIsS4RevealLoading] = useState(false)
  const [isS4Revealing, setIsS4Revealing] = useState(false)
  const [isS4RevealSelectingAllMatching, setIsS4RevealSelectingAllMatching] = useState(false)
  const pipelineRequestRef = useRef(0)
  const pipelineForegroundRequestRef = useRef(0)
  const pipelineSelectAllRequestRef = useRef(0)
  const pipelineSelectAllForegroundRequestRef = useRef(0)
  const s4RequestRef = useRef(0)
  const s4ForegroundRequestRef = useRef(0)
  const s4RevealRequestRef = useRef(0)
  const s4RevealForegroundRequestRef = useRef(0)
  const s4RevealSelectAllRequestRef = useRef(0)
  const s4RevealSelectAllForegroundRequestRef = useRef(0)
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

  const invalidateS4RevealSelectAllRequest = useCallback(() => {
    s4RevealSelectAllRequestRef.current += 1
    s4RevealSelectAllForegroundRequestRef.current = s4RevealSelectAllRequestRef.current
    setIsS4RevealSelectingAllMatching(false)
  }, [])

  const cancelStaleSelectAllRequests = useCallback(() => {
    invalidatePipelineSelectAllRequest()
    invalidateFullPipelineSelectAllRequest()
    invalidateS4RevealSelectAllRequest()
  }, [
    invalidateFullPipelineSelectAllRequest,
    invalidatePipelineSelectAllRequest,
    invalidateS4RevealSelectAllRequest,
  ])

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
      s4RevealRequestRef.current += 1
      setS4DiscoveredContacts(null)
      setS4DiscoveredCounts(null)
      setS4RevealLetterCounts({})
      setIsS4RevealLoading(false)
      return
    }
    const requestId = s4RevealRequestRef.current + 1
    s4RevealRequestRef.current = requestId
    s4RevealForegroundRequestRef.current = requestId
    setIsS4RevealLoading(true)
    try {
      const titleMatch =
        s4MatchFilter === 'matched' ? true :
        s4MatchFilter === 'unmatched' ? false :
        undefined
      const [contacts, letterCountsData, counts] = await Promise.all([
        listDiscoveredContacts({
          campaignId: selectedCampaignId,
          titleMatch,
          search: s4RevealSearch,
          staleEmailOnly: s4StaleEmailOnly,
          limit: s4RevealPageSize,
          offset: s4RevealOffset,
          sortBy: s4RevealSortBy,
          sortDir: s4RevealSortDir,
          letters: [...s4RevealActiveLetters],
        }),
        listDiscoveredContacts({
          campaignId: selectedCampaignId,
          titleMatch,
          search: s4RevealSearch,
          staleEmailOnly: s4StaleEmailOnly,
          limit: 1,
          offset: 0,
          countByLetters: true,
        }),
        getDiscoveredContactCounts(selectedCampaignId),
      ])
      if (s4RevealRequestRef.current !== requestId) return
      setS4DiscoveredContacts(contacts)
      setS4RevealLetterCounts(letterCountsData.letter_counts ?? {})
      setS4DiscoveredCounts(counts)
    } catch (err) {
      if (s4RevealRequestRef.current !== requestId) return
      setError(parseApiError(err))
    } finally {
      if (s4RevealForegroundRequestRef.current === requestId) {
        setIsS4RevealLoading(false)
      }
    }
  }, [
    requestsEnabled,
    selectedCampaignId,
    s4MatchFilter,
    s4RevealOffset,
    s4RevealPageSize,
    s4RevealSearch,
    s4StaleEmailOnly,
    s4RevealSortBy,
    s4RevealSortDir,
    s4RevealActiveLetters,
    setError,
  ])

  const loadS4RevealViewRef = useRef(loadS4RevealView)
  useEffect(() => { loadS4RevealViewRef.current = loadS4RevealView }, [loadS4RevealView])

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
    pipelineSortUserOverrideRef.current = false
    s4RevealSortUserOverrideRef.current = false
    s5ContactSortUserOverrideRef.current = false
    const defaultDecisionFilter: DecisionFilter = activeView === 's3-contacts' ? 'labeled' : 'all'
    const query = getPipelineCompanyQuery(activeView, defaultDecisionFilter)
    if (query !== null) {
      const defaultScrapeSubFilter = getDefaultPipelineScrapeSubFilter(activeView)
      const defaultScrapeFilter = scrapeSubToFilter(defaultScrapeSubFilter)
      const d = defaultCompanySortForStageView(activeView, statsRef.current)
      setPipelineSelectedIds([])
      skipNextPipelineLetterReloadRef.current = true
      setPipelineActiveLetters(new Set())
      setPipelineSearch('')
      setPipelineDecisionFilter(defaultDecisionFilter)
      setPipelineManualLabelActionState({})
      setPipelineScrapeSubFilter(defaultScrapeSubFilter)
      setPipelineOffset(0)
      setPipelinePageSize(DEFAULT_PAGE_SIZE)
      setPipelineSortBy(d.sortBy)
      setPipelineSortDir(d.sortDir)
      void loadPipelineView(
        query.stageFilter,
        query.decisionFilter,
        defaultScrapeFilter,
        d.sortBy,
        d.sortDir,
        DEFAULT_PAGE_SIZE,
        0,
        [],
        '',
      )
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
      s4RevealRequestRef.current += 1
      setS4DiscoveredSelectedIds([])
      setS4MatchFilter('all')
      setS4RevealOffset(0)
      const dr = defaultDiscoveredSort(statsRef.current)
      setS4RevealSortBy(dr.sortBy)
      setS4RevealSortDir(dr.sortDir)
      void loadS4RevealViewRef.current()
    } else if (activeView === 's5-validation') {
      setS4SelectedContactIds([])
      skipNextS4LetterReloadRef.current = true
      setS4ActiveLetters(new Set())
      setS4VerifFilter('valid')
      setS4Offset(0)
      setS4PageSize(DEFAULT_PAGE_SIZE)
      const dv = defaultValidationContactSort(statsRef.current)
      setS4SortBy(dv.sortBy)
      setS4SortDir(dv.sortDir)
      void loadS4View(dv.sortBy, dv.sortDir, 'valid', DEFAULT_PAGE_SIZE, 0, [])
    }
  }, [activeView, cancelStaleSelectAllRequests, loadPipelineView, loadFullPipelineView, loadS4View])

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
      pipelineSortUserOverrideRef.current = true
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

  /** When polling stats marks a stage "started", flip S1-S3 toward MRU sort unless user chose a header sort. */
  useEffect(() => {
    if (!requestsEnabled || !selectedCampaignId) return
    if (!['s1-scraping', 's2-ai', 's3-contacts'].includes(activeView)) return
    if (pipelineSortUserOverrideRef.current) return
    const query = getPipelineCompanyQuery(activeView, pipelineDecisionFilter)
    if (!query) return
    const next = defaultCompanySortForStageView(activeView, stats)
    if (next.sortBy === pipelineSortBy && next.sortDir === pipelineSortDir) return
    setPipelineSortBy(next.sortBy)
    setPipelineSortDir(next.sortDir)
    setPipelineOffset(0)
    const sf = scrapeSubToFilter(pipelineScrapeSubFilter)
    void loadPipelineView(
      query.stageFilter,
      query.decisionFilter,
      sf,
      next.sortBy,
      next.sortDir,
      pipelinePageSize,
      0,
      [...pipelineActiveLetters],
      pipelineSearch,
    )
  }, [
    stats,
    activeView,
    requestsEnabled,
    selectedCampaignId,
    pipelineDecisionFilter,
    pipelineScrapeSubFilter,
    pipelinePageSize,
    pipelineActiveLetters,
    pipelineSearch,
    loadPipelineView,
    pipelineSortBy,
    pipelineSortDir,
  ])

  /** Align S4 default sort when reveal queues start warming up. */
  useEffect(() => {
    if (!requestsEnabled || !selectedCampaignId || activeView !== 's4-reveal') return
    if (s4RevealSortUserOverrideRef.current) return
    const next = defaultDiscoveredSort(stats)
    if (next.sortBy === s4RevealSortBy && next.sortDir === s4RevealSortDir) return
    setS4RevealSortBy(next.sortBy)
    setS4RevealSortDir(next.sortDir)
    setS4RevealOffset(0)
  }, [stats, activeView, requestsEnabled, selectedCampaignId, s4RevealSortBy, s4RevealSortDir])

  /** Align S5 default sort when validation queues show activity. */
  useEffect(() => {
    if (!requestsEnabled || !selectedCampaignId || activeView !== 's5-validation') return
    if (s5ContactSortUserOverrideRef.current) return
    const next = defaultValidationContactSort(stats)
    if (next.sortBy === s4SortBy && next.sortDir === s4SortDir) return
    setS4SortBy(next.sortBy)
    setS4SortDir(next.sortDir)
    setS4Offset(0)
    void loadS4View(next.sortBy, next.sortDir, s4VerifFilter, s4PageSize, 0, [...s4ActiveLetters])
  }, [
    stats,
    activeView,
    requestsEnabled,
    selectedCampaignId,
    s4SortBy,
    s4SortDir,
    s4VerifFilter,
    s4PageSize,
    s4ActiveLetters,
    loadS4View,
  ])

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
          `Queued contact discovery for ${result.queued_count} compan${result.queued_count === 1 ? 'y' : 'ies'}.`,
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
    pipelineSearch,
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
  // Only react to S4 letter changes (and view switches into S5).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeView, s4ActiveLetters, loadS4View])

  useEffect(() => {
    if (activeView !== 's4-reveal' || !selectedCampaignId) return
    void loadS4RevealView()
  }, [activeView, selectedCampaignId, s4MatchFilter, s4RevealOffset, loadS4RevealView])

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
        setNotice(`Resumed S3 for ${company.domain}. Queued ${result.queued_count} contact discovery job(s).`)
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
      s5ContactSortUserOverrideRef.current = true
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
    invalidateS4RevealSelectAllRequest()
    setS4DiscoveredSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }, [invalidateS4RevealSelectAllRequest])

  const onS4ToggleAllDiscovered = useCallback((ids: string[]) => {
    invalidateS4RevealSelectAllRequest()
    setS4DiscoveredSelectedIds(ids)
  }, [invalidateS4RevealSelectAllRequest])

  const onS4ClearDiscoveredSelection = useCallback(() => {
    invalidateS4RevealSelectAllRequest()
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest])

  const onS4MatchFilterChange = useCallback((f: 'all' | 'matched' | 'unmatched') => {
    invalidateS4RevealSelectAllRequest()
    setS4MatchFilter(f)
    setS4RevealOffset(0)
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest])

  const onS4RevealSearchChange = useCallback((value: string) => {
    invalidateS4RevealSelectAllRequest()
    setS4RevealSearch(value)
    setS4RevealOffset(0)
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest])

  const onS4RevealToggleLetter = useCallback((letter: string) => {
    invalidateS4RevealSelectAllRequest()
    setS4RevealActiveLetters((prev) => {
      const next = new Set(prev)
      if (next.has(letter)) next.delete(letter)
      else next.add(letter)
      return next
    })
    setS4RevealOffset(0)
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest])

  const onS4RevealClearLetters = useCallback(() => {
    invalidateS4RevealSelectAllRequest()
    setS4RevealActiveLetters(new Set())
    setS4RevealOffset(0)
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest])

  const onS4RevealPagePrev = useCallback(() => {
    invalidateS4RevealSelectAllRequest()
    setS4RevealOffset((prev) => Math.max(0, prev - s4RevealPageSize))
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest, s4RevealPageSize])

  const onS4RevealPageNext = useCallback(() => {
    invalidateS4RevealSelectAllRequest()
    setS4RevealOffset((prev) => prev + s4RevealPageSize)
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest, s4RevealPageSize])

  const onS4RevealPageSizeChange = useCallback((size: number) => {
    invalidateS4RevealSelectAllRequest()
    setS4RevealPageSize(size)
    setS4RevealOffset(0)
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest])

  const onS4RevealSort = useCallback((field: string) => {
    invalidateS4RevealSelectAllRequest()
    s4RevealSortUserOverrideRef.current = true
    const newDir: 'asc' | 'desc' =
      s4RevealSortBy === field
        ? s4RevealSortDir === 'asc'
          ? 'desc'
          : 'asc'
        : SORT_DESC_FIRST.has(field)
          ? 'desc'
          : 'asc'
    setS4RevealSortBy(field)
    setS4RevealSortDir(newDir)
    setS4RevealOffset(0)
    setS4DiscoveredSelectedIds([])
  }, [invalidateS4RevealSelectAllRequest, s4RevealSortBy, s4RevealSortDir])

  const s4RevealSelectAllMatchingAsync = useCallback(async () => {
    if (!selectedCampaignId) {
      setError('Select a campaign first.')
      return
    }
    const requestId = s4RevealSelectAllRequestRef.current + 1
    s4RevealSelectAllRequestRef.current = requestId
    s4RevealSelectAllForegroundRequestRef.current = requestId
    const titleMatch =
      s4MatchFilter === 'matched' ? true :
      s4MatchFilter === 'unmatched' ? false :
      undefined

    setError('')
    setNotice('')
    setIsS4RevealSelectingAllMatching(true)
    try {
      const result = await listDiscoveredContactIds({
        campaignId: selectedCampaignId,
        titleMatch,
        search: s4RevealSearch,
        staleEmailOnly: s4StaleEmailOnly,
        letters: [...s4RevealActiveLetters],
      })
      if (s4RevealSelectAllRequestRef.current !== requestId) return
      const ids = result.ids.map((id) => String(id))
      setS4DiscoveredSelectedIds(ids)
      setNotice(
        ids.length > 0
          ? `Selected ${ids.length.toLocaleString()} discovered contact${ids.length === 1 ? '' : 's'} matching filters.`
          : 'No discovered contacts match these filters for the current list scope.',
      )
    } catch (err) {
      if (s4RevealSelectAllRequestRef.current !== requestId) return
      setError(parseApiError(err))
    } finally {
      if (s4RevealSelectAllForegroundRequestRef.current === requestId) {
        setIsS4RevealSelectingAllMatching(false)
      }
    }
  }, [
    selectedCampaignId,
    s4MatchFilter,
    s4RevealSearch,
    s4StaleEmailOnly,
    s4RevealActiveLetters,
    setError,
    setNotice,
  ])

  const onS4RevealSelectAllMatching = useCallback(() => {
    void s4RevealSelectAllMatchingAsync()
  }, [s4RevealSelectAllMatchingAsync])

  const onS4RevealSelected = useCallback(async () => {
    if (!selectedCampaignId || !s4DiscoveredSelectedIds.length) return
    invalidateS4RevealSelectAllRequest()
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
  }, [
    selectedCampaignId,
    s4DiscoveredSelectedIds,
    invalidateS4RevealSelectAllRequest,
    loadS4RevealView,
    setError,
    setNotice,
  ])

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
    s4RevealLetterCounts,
    s4RevealActiveLetters,
    s4DiscoveredSelectedIds,
    s4MatchFilter,
    s4RevealSearch,
    s4RevealOffset,
    s4RevealPageSize,
    s4RevealSortBy,
    s4RevealSortDir,
    s4StaleEmailOnly,
    isS4RevealLoading,
    isS4Revealing,
    isS4RevealSelectingAllMatching,
    onS4ToggleDiscovered,
    onS4ToggleAllDiscovered,
    onS4ClearDiscoveredSelection,
    onS4MatchFilterChange,
    onS4RevealSearchChange,
    onS4RevealToggleLetter,
    onS4RevealClearLetters,
    onS4RevealPagePrev,
    onS4RevealPageNext,
    onS4RevealPageSizeChange,
    onS4RevealSort,
    onS4RevealSelectAllMatching,
    onS4RevealSelected: () => { void onS4RevealSelected() },
    onS4StaleEmailOnlyChange: (v: boolean) => {
      setS4StaleEmailOnly(v)
      setS4RevealOffset(0)
      setS4DiscoveredSelectedIds([])
    },
  }
}
