import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createEmailFetchBatch,
  getActiveEmailFetchBatch,
  getEmailFetchCriteria,
  getEmailFetchLetterCounts,
  listEmailFetchCompanyIds,
  listEmailFetchCompanies,
  previewEmailFetch,
} from '../../../lib/api'
import type {
  DomainLetterCounts,
  EmailFetchBatchRead,
  EmailFetchCompanyCounts,
  EmailFetchCompanyRow,
  EmailFetchCompanyStatus,
  EmailFetchCriteriaRead,
  EmailFetchMode,
  EmailFetchPreviewRead,
} from '../../../lib/types'
import { createQueryRequestGate } from '../../../lib/requestGate'
import { useCampaignEventStream } from '../../../lib/useCampaignEventStream'
import { parseApiError } from '../../../lib/utils'
import { StageViewHeader }        from '../shared/StageViewHeader'
import { StageToolbar }           from '../shared/StageToolbar'
import { ContactsTable }          from './ContactsTable'
import { ContactsCards }          from './ContactsCards'
import { ContactDrawer }          from './ContactDrawer'
import { ContactsSettingsDrawer } from './ContactsSettingsDrawer'
import { EmailFetchPreviewDialog } from './EmailFetchPreviewDialog'
import { Loader2 } from 'lucide-react'

type FilterValue = 'all' | EmailFetchCompanyStatus

const PAGE_SIZE = 50
const MAX_FETCH_BATCH_SIZE = 200
const POLL_STATUS_ACTIVE_MS = 4000
const POLL_HEAVY_ACTIVE_MS = 10000
const POLL_STATUS_BG_MS = 20000
const POLL_HEAVY_BG_MS = 30000
const LETTERS = ['#', ...Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i))]

const EMPTY_COUNTS: EmailFetchCompanyCounts = {
  all: 0,
  pending: 0,
  running: 0,
  done: 0,
  failed: 0,
  no_match: 0,
  contacts_found: 0,
  emails_found: 0,
  fetched_people_found: 0,
}

function canFetch(row: EmailFetchCompanyRow): boolean {
  return row.status === 'pending' || row.status === 'failed'
}

function canRefetch(row: EmailFetchCompanyRow): boolean {
  return row.status === 'done' || row.status === 'no_match'
}

interface ContactsViewProps {
  campaignId: string
  onStageCountsRefresh?: () => void
  onActiveBatchChange?: (batch: EmailFetchBatchRead | null) => void
  onContactCountsChange?: (counts: EmailFetchCompanyCounts | null) => void
}

export function ContactsView({
  campaignId,
  onStageCountsRefresh,
  onActiveBatchChange,
  onContactCountsChange,
}: ContactsViewProps) {
  const [filter, setFilter] = useState<FilterValue>('all')
  const [letterFilter, setLetterFilter] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<EmailFetchCompanyRow[]>([])
  const [companyTotal, setCompanyTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [letterCounts, setLetterCounts] = useState<DomainLetterCounts | null>(null)
  const [counts, setCounts] = useState<EmailFetchCompanyCounts>(EMPTY_COUNTS)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState('')

  const [criteria, setCriteria] = useState<EmailFetchCriteriaRead | null>(null)
  const [criteriaLoading, setCriteriaLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [allMatchingSelected, setAllMatchingSelected] = useState(false)
  const [matchingSelectionTotal, setMatchingSelectionTotal] = useState(0)
  const [viewingRow, setViewingRow] = useState<EmailFetchCompanyRow | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewDomainIds, setPreviewDomainIds] = useState<string[]>([])
  const [previewMode, setPreviewMode] = useState<EmailFetchMode>('fetch')
  const [preview, setPreview] = useState<EmailFetchPreviewRead | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const [isConfirming, setIsConfirming] = useState(false)
  const [activeBatch, setActiveBatch] = useState<EmailFetchBatchRead | null>(null)
  const rowsRequestGate = useMemo(() => createQueryRequestGate(), [])
  const letterCountsRequestGate = useMemo(() => createQueryRequestGate(), [])
  const isVisibleRef = useRef<boolean>(typeof document === 'undefined' ? true : document.visibilityState === 'visible')
  const statusPollBusyRef = useRef(false)
  const heavyPollBusyRef = useRef(false)
  const activeBatchRef = useRef<EmailFetchBatchRead | null>(null)

  const hasTitleRules = (criteria?.include_titles.length ?? 0) > 0
  const activeBatchCriteriaChanged = Boolean(
    activeBatch?.criteria_hash &&
    criteria?.criteria_hash &&
    activeBatch.criteria_hash !== criteria.criteria_hash,
  )
  const activeBatchCriteriaTime = activeBatch?.created_at
    ? new Date(activeBatch.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : 'batch start'
  const normalizedSearch = search.trim()
  const isGlobalCountScope = filter === 'all' && letterFilter === 'all' && !normalizedSearch
  const rowsQueryKey = useMemo(() => JSON.stringify({
    campaignId,
    filter,
    letterFilter,
    page,
    search: normalizedSearch,
  }), [campaignId, filter, letterFilter, normalizedSearch, page])
  const rowsQueryKeyRef = useRef(rowsQueryKey)
  rowsQueryKeyRef.current = rowsQueryKey
  const letterCountsQueryKey = useMemo(() => JSON.stringify({
    campaignId,
    filter,
    search: normalizedSearch,
  }), [campaignId, filter, normalizedSearch])
  const letterCountsQueryKeyRef = useRef(letterCountsQueryKey)
  letterCountsQueryKeyRef.current = letterCountsQueryKey

  useEffect(() => {
    activeBatchRef.current = activeBatch
  }, [activeBatch])

  useEffect(() => {
    onActiveBatchChange?.(activeBatch)
  }, [activeBatch, onActiveBatchChange])

  useEffect(() => {
    return () => onActiveBatchChange?.(null)
  }, [onActiveBatchChange])

  const loadCriteria = useCallback(async () => {
    setCriteriaLoading(true)
    try {
      setCriteria(await getEmailFetchCriteria(campaignId))
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setCriteriaLoading(false)
    }
  }, [campaignId])

  const loadActiveBatch = useCallback(async () => {
    try {
      setActiveBatch(await getActiveEmailFetchBatch(campaignId))
    } catch {
      setActiveBatch(null)
    }
  }, [campaignId])

  const loadRows = useCallback(async (quiet = false) => {
    const requestToken = rowsRequestGate.start(rowsQueryKey)
    const isCurrentResponse = () => rowsRequestGate.isCurrent(requestToken, rowsQueryKeyRef.current)
    if (quiet) {
      setIsRefreshing(true)
    } else {
      setIsLoading(true)
      setIsRefreshing(false)
    }
    setError('')
    try {
      const res = await listEmailFetchCompanies(campaignId, {
        status: filter,
        search,
        letter: letterFilter !== 'all' ? letterFilter : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      if (!isCurrentResponse()) return
      setRows(res.items)
      setCompanyTotal(res.total)
      setCounts(res.counts)
      if (isGlobalCountScope) {
        onContactCountsChange?.(res.counts)
      }
    } catch (err) {
      if (!isCurrentResponse()) return
      setError(parseApiError(err))
      setRows([])
      setCompanyTotal(0)
      setCounts(EMPTY_COUNTS)
    } finally {
      if (!isCurrentResponse()) return
      setIsRefreshing(false)
      setIsLoading(false)
    }
  }, [campaignId, filter, isGlobalCountScope, letterFilter, onContactCountsChange, page, rowsQueryKey, rowsRequestGate, search])

  const loadLetterCounts = useCallback(async () => {
    const requestToken = letterCountsRequestGate.start(letterCountsQueryKey)
    const isCurrentResponse = () => letterCountsRequestGate.isCurrent(requestToken, letterCountsQueryKeyRef.current)
    try {
      const res = await getEmailFetchLetterCounts(campaignId, { status: filter, search })
      if (!isCurrentResponse()) return
      setLetterCounts(res)
    } catch {
      if (!isCurrentResponse()) return
      setLetterCounts(null)
    }
  }, [campaignId, filter, letterCountsQueryKey, letterCountsRequestGate, search])

  useEffect(() => { void loadCriteria() }, [loadCriteria])
  useEffect(() => { void loadRows(false) }, [loadRows])
  useEffect(() => { void loadLetterCounts() }, [loadLetterCounts])
  useEffect(() => { void loadActiveBatch() }, [loadActiveBatch])
  useEffect(() => { onStageCountsRefresh?.() }, [campaignId, onStageCountsRefresh])

  useEffect(() => {
    if (typeof document === 'undefined') return
    const onVisibilityChange = () => {
      const wasVisible = isVisibleRef.current
      isVisibleRef.current = document.visibilityState === 'visible'
      if (!wasVisible && isVisibleRef.current) {
        void Promise.all([loadRows(true), loadLetterCounts(), loadActiveBatch()])
        onStageCountsRefresh?.()
      }
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [loadActiveBatch, loadLetterCounts, loadRows, onStageCountsRefresh])

  useEffect(() => {
    let cancelled = false
    let statusTimer: number | null = null
    let heavyTimer: number | null = null

    const jitterMs = () => 200 + Math.floor(Math.random() * 201)
    const statusInterval = () => (isVisibleRef.current ? POLL_STATUS_ACTIVE_MS : POLL_STATUS_BG_MS)
    const heavyInterval = () => (isVisibleRef.current ? POLL_HEAVY_ACTIVE_MS : POLL_HEAVY_BG_MS)

    const scheduleStatus = (delayMs?: number) => {
      if (cancelled) return
      statusTimer = window.setTimeout(() => { void runStatusTick() }, delayMs ?? (statusInterval() + jitterMs()))
    }
    const scheduleHeavy = (delayMs?: number) => {
      if (cancelled) return
      heavyTimer = window.setTimeout(() => { void runHeavyTick() }, delayMs ?? (heavyInterval() + jitterMs()))
    }

    const runHeavyTick = async () => {
      if (cancelled) return
      if (heavyPollBusyRef.current) {
        scheduleHeavy(heavyInterval())
        return
      }
      if (!activeBatchRef.current && !isConfirming) {
        scheduleHeavy(heavyInterval())
        return
      }
      heavyPollBusyRef.current = true
      try {
        await Promise.all([loadRows(true), loadLetterCounts()])
        onStageCountsRefresh?.()
      } finally {
        heavyPollBusyRef.current = false
        scheduleHeavy()
      }
    }

    const runStatusTick = async () => {
      if (cancelled) return
      if (statusPollBusyRef.current) {
        scheduleStatus(statusInterval())
        return
      }
      if (!activeBatchRef.current && !isConfirming) {
        scheduleStatus(statusInterval())
        return
      }
      statusPollBusyRef.current = true
      try {
        const discovered = await getActiveEmailFetchBatch(campaignId).catch(() => null)
        setActiveBatch(discovered)
        if (!discovered && activeBatchRef.current) {
          await Promise.all([loadRows(true), loadLetterCounts()])
          onStageCountsRefresh?.()
        }
      } finally {
        statusPollBusyRef.current = false
        scheduleStatus()
      }
    }

    void runStatusTick()
    void runHeavyTick()
    return () => {
      cancelled = true
      if (statusTimer !== null) window.clearTimeout(statusTimer)
      if (heavyTimer !== null) window.clearTimeout(heavyTimer)
    }
  }, [campaignId, isConfirming, loadLetterCounts, loadRows, onStageCountsRefresh])

  useCampaignEventStream(campaignId, (event) => {
    const isEmailFetchEvent = event.stage === 's3' || event.event_type === 'email_fetch_batch'
    if (!isEmailFetchEvent) return
    onStageCountsRefresh?.()
    void Promise.all([loadRows(true), loadLetterCounts(), loadActiveBatch()])
  })

  const selectedFetchableIds = useMemo(
    () => allMatchingSelected
      ? [...selected]
      : rows.filter((row) => selected.has(row.domain_id) && canFetch(row)).map((row) => row.domain_id),
    [allMatchingSelected, rows, selected],
  )
  const selectedRefetchIds = useMemo(
    () => rows.filter((row) => selected.has(row.domain_id) && canRefetch(row)).map((row) => row.domain_id),
    [rows, selected],
  )

  const letterAllTotal = useMemo(() => {
    if (!letterCounts) return companyTotal
    return Object.values(letterCounts.counts).reduce((sum, count) => sum + count, 0)
  }, [companyTotal, letterCounts])

  const contactStats = useMemo(() => {
    return [
      { label: 'pending',  value: counts.pending,  color: 'var(--oc-muted)' },
      { label: 'fetching', value: counts.running,  color: 'var(--s3)', live: counts.running > 0 },
      { label: 'done',     value: counts.done,     color: 'var(--oc-success-text)' },
      { label: 'contacts', value: counts.contacts_found, color: 'var(--s3)' },
      { label: 'emails',   value: counts.emails_found,   color: 'var(--oc-success-text)' },
      { label: 'fetched',  value: counts.fetched_people_found, color: 'var(--oc-muted)' },
    ]
  }, [counts])

  const filters = useMemo(() => [
    { value: 'all',      label: 'All',      count: counts.all },
    { value: 'pending',  label: 'Pending',  count: counts.pending },
    { value: 'running',  label: 'Fetching', count: counts.running,  color: 'var(--s3)' },
    { value: 'done',     label: 'Done',     count: counts.done,     color: 'var(--oc-success-text)' },
    { value: 'failed',   label: 'Failed',   count: counts.failed,   color: 'var(--oc-fail-text)' },
    { value: 'no_match', label: 'No match', count: counts.no_match, color: 'var(--oc-warn-text)' },
  ], [counts])

  const matchingFetchableCount = filter === 'all'
    ? counts.pending + counts.failed
    : filter === 'pending' || filter === 'failed'
      ? companyTotal
      : 0
  const totalPages = Math.ceil(companyTotal / PAGE_SIZE)
  const pendingFetchCount = counts.pending
  const pendingFetchBatchCount = Math.min(MAX_FETCH_BATCH_SIZE, pendingFetchCount)
  const pendingFetchLabel = pendingFetchCount > MAX_FETCH_BATCH_SIZE
    ? `Fetch ${MAX_FETCH_BATCH_SIZE} of ${pendingFetchCount.toLocaleString()} pending`
    : `Fetch ${pendingFetchCount.toLocaleString()} pending`

  function toggleSelect(id: string) {
    setAllMatchingSelected(false)
    setMatchingSelectionTotal(0)
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    setAllMatchingSelected(false)
    setMatchingSelectionTotal(0)
    if (rows.every((row) => selected.has(row.domain_id))) {
      setSelected(new Set())
    } else {
      setSelected(new Set(rows.map((row) => row.domain_id)))
    }
  }

  function clearSelection() {
    setAllMatchingSelected(false)
    setMatchingSelectionTotal(0)
    setSelected(new Set())
  }

  function resetViewControls() {
    setPage(0)
    clearSelection()
  }

  function goToPage(nextPage: number) {
    setPage(nextPage)
    if (!allMatchingSelected) {
      setSelected(new Set())
      setMatchingSelectionTotal(0)
    }
  }

  async function resolveFetchableIds({
    status,
    limit = MAX_FETCH_BATCH_SIZE,
  }: {
    status: FilterValue
    limit?: number
  }): Promise<{ ids: string[]; total: number }> {
    const res = await listEmailFetchCompanyIds(campaignId, {
      status,
      search,
      letter: letterFilter !== 'all' ? letterFilter : undefined,
      fetchableOnly: true,
      limit,
    })
    return { ids: res.ids, total: res.total }
  }

  async function selectMatchingFetchable() {
    if (matchingFetchableCount === 0 || busy) return
    setError('')
    try {
      const resolved = await resolveFetchableIds({ status: filter })
      setSelected(new Set(resolved.ids))
      setAllMatchingSelected(true)
      setMatchingSelectionTotal(resolved.total)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  function startPreview(domainIds: string[], mode: EmailFetchMode = 'fetch') {
    const uniqueIds = [...new Set(domainIds)].slice(0, MAX_FETCH_BATCH_SIZE)
    if (uniqueIds.length === 0) return
    if (!hasTitleRules) {
      setSettingsOpen(true)
      return
    }
    setPreviewOpen(true)
    setPreviewDomainIds(uniqueIds)
    setPreviewMode(mode)
    setPreview(null)
    setPreviewError('')
    setPreviewLoading(true)
    void previewEmailFetch({ campaign_id: campaignId, domain_ids: uniqueIds, mode })
      .then(setPreview)
      .catch((err) => setPreviewError(parseApiError(err)))
      .finally(() => setPreviewLoading(false))
  }

  async function startPendingPreview() {
    if (pendingFetchBatchCount === 0 || fetchDisabled) return
    setError('')
    try {
      const resolved = await resolveFetchableIds({ status: 'pending' })
      startPreview(resolved.ids)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  async function confirmPreview() {
    if (previewDomainIds.length === 0) return
    setIsConfirming(true)
    setPreviewError('')
    try {
      const batch = await createEmailFetchBatch({ campaign_id: campaignId, domain_ids: previewDomainIds, mode: previewMode })
      setActiveBatch(batch)
      onStageCountsRefresh?.()
      setPreviewOpen(false)
      clearSelection()
      await Promise.all([loadRows(true), loadLetterCounts(), loadActiveBatch()])
    } catch (err) {
      setPreviewError(parseApiError(err))
    } finally {
      setIsConfirming(false)
    }
  }

  const busy = previewLoading || isConfirming || Boolean(activeBatch)
  const fetchDisabled = busy || criteriaLoading || !hasTitleRules
  const bulkActions = [
    ...(selectedFetchableIds.length > 0
      ? [{ label: `Fetch ${selectedFetchableIds.length}`, onClick: () => startPreview(selectedFetchableIds) }]
      : []),
    ...(selectedRefetchIds.length > 0
      ? [{ label: `Refetch ${selectedRefetchIds.length}`, onClick: () => startPreview(selectedRefetchIds, 'refetch') }]
      : []),
  ]

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <StageViewHeader
          stageNum="S3"
          stageLabel="Contacts & Email"
          stageColor="var(--s3)"
          stageBg="var(--s3-bg)"
          stats={contactStats}
          onOpenSettings={() => setSettingsOpen(true)}
          settingsLabel="Title rules"
          primaryAction={pendingFetchCount > 0 ? {
            label: pendingFetchLabel,
            disabled: fetchDisabled,
            onClick: () => { void startPendingPreview() },
          } : undefined}
          secondaryAction={counts.failed > 0 ? {
            label: `Retry ${counts.failed} failed`,
            onClick: () => { setFilter('failed'); resetViewControls() },
          } : undefined}
        />

        {activeBatchCriteriaChanged && (
          <div className="oc-panel" style={{
            padding: '0.75rem 0.875rem',
            borderColor: 'color-mix(in srgb, var(--s3) 35%, var(--oc-border))',
            background: 'color-mix(in srgb, var(--s3) 8%, var(--oc-surface))',
            color: 'var(--oc-text)',
            fontSize: '0.8125rem',
          }}>
            Fetch running with rules from {activeBatchCriteriaTime}. New title rules apply to future fetches.
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', position: 'relative' }}>
          {['all', ...LETTERS].map((l) => {
            const count = l === 'all' ? letterAllTotal : (letterCounts?.counts[l] ?? 0)
            const active = letterFilter === l
            return (
              <button
                key={l}
                type="button"
                onClick={() => {
                  setLetterFilter(l)
                  resetViewControls()
                }}
                style={{
                  padding: '0.25rem 0.5rem', borderRadius: '0.375rem', fontSize: '0.75rem',
                  fontWeight: active ? 700 : 500, fontFamily: 'var(--font-mono)',
                  background: active ? 'var(--s3)' : 'var(--oc-surface)',
                  color: active ? '#fff' : count > 0 ? 'var(--oc-text)' : 'var(--oc-muted)',
                  border: active ? '1.5px solid var(--s3)' : '1.5px solid var(--oc-border)',
                  cursor: count > 0 || l === 'all' ? 'pointer' : 'default',
                  opacity: count === 0 && l !== 'all' ? 0.4 : 1,
                  minWidth: '2rem', textAlign: 'center',
                }}
              >
                {l}
                {count > 0 && (
                  <span style={{ marginLeft: '0.25rem', fontWeight: 400, opacity: 0.75 }}>
                    {count > 999 ? `${Math.floor(count / 1000)}k` : count}
                  </span>
                )}
              </button>
            )
          })}
        </div>

        <StageToolbar
          stageColor="var(--s3)"
          filters={filters}
          activeFilter={filter}
          onFilterChange={(v) => {
            setFilter(v as FilterValue)
            resetViewControls()
          }}
          search={search}
          onSearchChange={(value) => {
            setSearch(value)
            resetViewControls()
          }}
          selectedCount={selected.size}
          bulkActions={bulkActions}
          onClearSelection={clearSelection}
        />

        {matchingFetchableCount > 0 && !busy && (
          <button
            type="button"
            onClick={() => { void selectMatchingFetchable() }}
            style={{
              alignSelf: 'flex-start',
              border: 'none',
              background: 'none',
              color: 'var(--s3)',
              cursor: 'pointer',
              fontSize: '0.8125rem',
              fontWeight: 700,
              padding: '0 0.125rem',
              textDecoration: 'underline',
              textUnderlineOffset: '2px',
            }}
          >
            {allMatchingSelected
              ? matchingSelectionTotal > MAX_FETCH_BATCH_SIZE
                ? `First ${MAX_FETCH_BATCH_SIZE} of ${matchingSelectionTotal.toLocaleString()} matching selected`
                : `All ${matchingSelectionTotal.toLocaleString()} matching selected`
              : matchingFetchableCount > MAX_FETCH_BATCH_SIZE
                ? `Select first ${MAX_FETCH_BATCH_SIZE} of ${matchingFetchableCount.toLocaleString()} matching`
                : `Select all ${matchingFetchableCount.toLocaleString()} matching`}
          </button>
        )}

        {error && (
          <div className="oc-panel" style={{ color: 'var(--oc-fail-text)', padding: '0.875rem 1rem', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="oc-panel" style={{ padding: '2.5rem 1rem', color: 'var(--oc-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} />
            Loading companies
          </div>
        ) : rows.length === 0 ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            No companies match this filter.
          </div>
        ) : (
          <>
            {isRefreshing && (
              <div style={{ alignSelf: 'flex-end', display: 'inline-flex', gap: '0.375rem', alignItems: 'center', color: 'var(--oc-muted)', fontSize: '0.75rem' }}>
                <Loader2 size={12} style={{ animation: 'spin 0.7s linear infinite' }} />
                Refreshing
              </div>
            )}
            <div className="hidden md:block">
              <ContactsTable
                rows={rows}
                selected={selected}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                onFetch={(id) => startPreview([id])}
                onRefetch={(id) => startPreview([id], 'refetch')}
                onViewContacts={setViewingRow}
                fetchDisabled={fetchDisabled}
                hasActiveFilter={filter !== 'all' || letterFilter !== 'all' || Boolean(search.trim())}
                onClearFilter={() => {
                  setFilter('all')
                  setLetterFilter('all')
                  setSearch('')
                  resetViewControls()
                }}
              />
            </div>
            <div className="md:hidden">
              <ContactsCards
                rows={rows}
                selected={selected}
                onToggleSelect={toggleSelect}
                onFetch={(id) => startPreview([id])}
                onRefetch={(id) => startPreview([id], 'refetch')}
                onViewContacts={setViewingRow}
                fetchDisabled={fetchDisabled}
              />
            </div>
          </>
        )}

        {totalPages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              disabled={page === 0 || isLoading}
              onClick={() => goToPage(page - 1)}
              className="oc-btn oc-btn-secondary oc-btn-sm"
              style={{ opacity: page === 0 || isLoading ? 0.4 : 1 }}
            >
              ← Prev
            </button>
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', fontFamily: 'var(--font-mono)' }}>
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages - 1 || isLoading}
              onClick={() => goToPage(page + 1)}
              className="oc-btn oc-btn-secondary oc-btn-sm"
              style={{ opacity: page >= totalPages - 1 || isLoading ? 0.4 : 1 }}
            >
              Next →
            </button>
          </div>
        )}
      </div>

      <ContactDrawer campaignId={campaignId} row={viewingRow} onClose={() => setViewingRow(null)} />
      <ContactsSettingsDrawer
        campaignId={campaignId}
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={setCriteria}
      />
      <EmailFetchPreviewDialog
        open={previewOpen}
        preview={preview}
        loading={previewLoading}
        error={previewError}
        isConfirming={isConfirming}
        onClose={() => { if (!isConfirming) setPreviewOpen(false) }}
        onConfirm={() => void confirmPreview()}
      />
    </>
  )
}
