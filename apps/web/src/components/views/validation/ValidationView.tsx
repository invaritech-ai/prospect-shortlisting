import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createEmailVerificationBatch,
  downloadFreshValidEmailCsv,
  getActiveEmailVerificationBatch,
  getEmailVerificationLetterCounts,
  listEmailVerificationContactIds,
  listEmailVerificationContacts,
  previewEmailVerification,
} from '../../../lib/api'
import type {
  DomainLetterCounts,
  EmailVerificationBatchRead,
  EmailVerificationContactRow,
  EmailVerificationCounts,
  EmailVerificationPreviewRead,
  EmailVerificationStatus,
} from '../../../lib/types'
import { createQueryRequestGate } from '../../../lib/requestGate'
import { useCampaignEventStream } from '../../../lib/useCampaignEventStream'
import { parseApiError } from '../../../lib/utils'
import { StageViewHeader } from '../shared/StageViewHeader'
import { StageToolbar } from '../shared/StageToolbar'
import { ValidationTable } from './ValidationTable'
import { ValidationCards } from './ValidationCards'
import { EmailVerificationPreviewDialog } from './EmailVerificationPreviewDialog'
import { Loader2 } from 'lucide-react'
import { IconDownload } from '../../ui/icons'

type FilterValue = 'all' | EmailVerificationStatus

const PAGE_SIZE = 50
const MAX_VERIFICATION_BATCH_SIZE = 200
const POLL_STATUS_ACTIVE_MS = 4000
const POLL_HEAVY_ACTIVE_MS = 10000
const POLL_STATUS_BG_MS = 20000
const POLL_HEAVY_BG_MS = 30000
const LETTERS = ['#', ...Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i))]
const NO_SELECTED_ACTIONABLE_MESSAGE = 'No selected emails need validation. Fresh results can be revalidated after 30 days.'

const EMPTY_COUNTS: EmailVerificationCounts = {
  all: 0,
  pending: 0,
  checking: 0,
  stale: 0,
  valid: 0,
  undeliverable: 0,
  catch_all: 0,
  unknown: 0,
  failed: 0,
}

interface ValidationViewProps {
  campaignId: string
  onStageCountsRefresh?: () => void
  onActiveBatchChange?: (batch: EmailVerificationBatchRead | null) => void
}

export function ValidationView({
  campaignId,
  onStageCountsRefresh,
  onActiveBatchChange,
}: ValidationViewProps) {
  const [filter, setFilter] = useState<FilterValue>('all')
  const [letterFilter, setLetterFilter] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState<EmailVerificationContactRow[]>([])
  const [contactTotal, setContactTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [letterCounts, setLetterCounts] = useState<DomainLetterCounts | null>(null)
  const [counts, setCounts] = useState<EmailVerificationCounts>(EMPTY_COUNTS)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [allMatchingSelected, setAllMatchingSelected] = useState(false)
  const [matchingSelectionTotal, setMatchingSelectionTotal] = useState(0)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewContactIds, setPreviewContactIds] = useState<string[]>([])
  const [preview, setPreview] = useState<EmailVerificationPreviewRead | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const [isConfirming, setIsConfirming] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [activeBatch, setActiveBatch] = useState<EmailVerificationBatchRead | null>(null)
  const rowsRequestGate = useMemo(() => createQueryRequestGate(), [])
  const letterCountsRequestGate = useMemo(() => createQueryRequestGate(), [])
  const isVisibleRef = useRef<boolean>(typeof document === 'undefined' ? true : document.visibilityState === 'visible')
  const statusPollBusyRef = useRef(false)
  const heavyPollBusyRef = useRef(false)
  const activeBatchRef = useRef<EmailVerificationBatchRead | null>(null)
  const normalizedSearch = search.trim()
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

  const loadActiveBatch = useCallback(async () => {
    try {
      setActiveBatch(await getActiveEmailVerificationBatch(campaignId))
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
      const res = await listEmailVerificationContacts(campaignId, {
        status: filter,
        search,
        letter: letterFilter !== 'all' ? letterFilter : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      if (!isCurrentResponse()) return
      setRows(res.items)
      setContactTotal(res.total)
      setCounts(res.counts)
    } catch (err) {
      if (!isCurrentResponse()) return
      setError(parseApiError(err))
      setRows([])
      setContactTotal(0)
      setCounts(EMPTY_COUNTS)
    } finally {
      if (!isCurrentResponse()) return
      setIsRefreshing(false)
      setIsLoading(false)
    }
  }, [campaignId, filter, letterFilter, page, rowsQueryKey, rowsRequestGate, search])

  const loadLetterCounts = useCallback(async () => {
    const requestToken = letterCountsRequestGate.start(letterCountsQueryKey)
    const isCurrentResponse = () => letterCountsRequestGate.isCurrent(requestToken, letterCountsQueryKeyRef.current)
    try {
      const res = await getEmailVerificationLetterCounts(campaignId, { status: filter, search })
      if (!isCurrentResponse()) return
      setLetterCounts(res)
    } catch {
      if (!isCurrentResponse()) return
      setLetterCounts(null)
    }
  }, [campaignId, filter, letterCountsQueryKey, letterCountsRequestGate, search])

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
        const discovered = await getActiveEmailVerificationBatch(campaignId).catch(() => null)
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
    const isVerificationEvent = event.stage === 's4' || event.event_type === 'verification_batch'
    if (!isVerificationEvent) return
    onStageCountsRefresh?.()
    void Promise.all([loadRows(true), loadLetterCounts(), loadActiveBatch()])
  })

  const selectedActionableIds = useMemo(
    () => allMatchingSelected
      ? [...selected]
      : rows.filter((row) => selected.has(row.contact_id) && row.action_label).map((row) => row.contact_id),
    [allMatchingSelected, rows, selected],
  )

  const letterAllTotal = useMemo(() => {
    if (!letterCounts) return contactTotal
    return Object.values(letterCounts.counts).reduce((sum, count) => sum + count, 0)
  }, [contactTotal, letterCounts])

  const validationStats = useMemo(() => [
    { label: 'pending', value: counts.pending, color: 'var(--oc-muted)' },
    { label: 'checking', value: counts.checking, color: 'var(--s5)', live: counts.checking > 0 },
    { label: 'stale', value: counts.stale, color: 'var(--oc-warn-text)' },
    { label: 'valid', value: counts.valid, color: 'var(--oc-success-text)' },
    { label: 'undeliverable', value: counts.undeliverable, color: 'var(--oc-fail-text)' },
    { label: 'catch-all', value: counts.catch_all, color: 'var(--oc-warn-text)' },
    { label: 'unknown', value: counts.unknown, color: 'var(--oc-muted)' },
    { label: 'failed', value: counts.failed, color: 'var(--oc-fail-text)' },
  ], [counts])

  const filters = useMemo(() => [
    { value: 'all', label: 'All', count: counts.all },
    { value: 'pending', label: 'Pending', count: counts.pending },
    { value: 'checking', label: 'Checking', count: counts.checking, color: 'var(--s5)' },
    { value: 'stale', label: 'Stale', count: counts.stale, color: 'var(--oc-warn-text)' },
    { value: 'valid', label: 'Valid', count: counts.valid, color: 'var(--oc-success-text)' },
    { value: 'undeliverable', label: 'Undeliverable', count: counts.undeliverable, color: 'var(--oc-fail-text)' },
    { value: 'catch_all', label: 'Catch-all', count: counts.catch_all, color: 'var(--oc-warn-text)' },
    { value: 'unknown', label: 'Unknown', count: counts.unknown, color: 'var(--oc-muted)' },
    { value: 'failed', label: 'Failed', count: counts.failed, color: 'var(--oc-fail-text)' },
  ], [counts])

  const matchingActionableCount = filter === 'all'
    ? counts.pending + counts.stale + counts.failed
    : filter === 'pending' || filter === 'stale' || filter === 'failed'
      ? contactTotal
      : 0
  const validationBatchCount = Math.min(MAX_VERIFICATION_BATCH_SIZE, matchingActionableCount)
  const primaryValidationLabel = matchingActionableCount > MAX_VERIFICATION_BATCH_SIZE
    ? `Validate first ${MAX_VERIFICATION_BATCH_SIZE} actionable`
    : `Validate ${validationBatchCount.toLocaleString()} actionable`
  const totalPages = Math.ceil(contactTotal / PAGE_SIZE)
  const busy = previewLoading || isConfirming || Boolean(activeBatch)
  const previewSummary = preview ? {
    skipped_count: preview.skipped_count,
    cached_count: preview.cached_count,
    paid_validation_count: preview.paid_validation_count,
  } : null

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
    if (rows.length > 0 && rows.every((row) => selected.has(row.contact_id))) {
      setSelected(new Set())
    } else {
      setSelected(new Set(rows.map((row) => row.contact_id)))
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

  async function resolveActionableIds(limit = MAX_VERIFICATION_BATCH_SIZE): Promise<{ ids: string[]; total: number }> {
    const res = await listEmailVerificationContactIds(campaignId, {
      status: filter,
      search,
      letter: letterFilter !== 'all' ? letterFilter : undefined,
      actionableOnly: true,
      limit,
    })
    return { ids: res.ids, total: res.total }
  }

  async function selectMatchingActionable() {
    if (matchingActionableCount === 0 || busy) return
    setError('')
    try {
      const resolved = await resolveActionableIds()
      setSelected(new Set(resolved.ids))
      setAllMatchingSelected(true)
      setMatchingSelectionTotal(resolved.total)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  function startPreview(contactIds: string[]) {
    const uniqueIds = [...new Set(contactIds)].slice(0, MAX_VERIFICATION_BATCH_SIZE)
    if (uniqueIds.length === 0) return
    setPreviewOpen(true)
    setPreviewContactIds(uniqueIds)
    setPreview(null)
    setPreviewError('')
    setPreviewLoading(true)
    void previewEmailVerification({ campaign_id: campaignId, contact_ids: uniqueIds })
      .then(setPreview)
      .catch((err) => setPreviewError(parseApiError(err)))
      .finally(() => setPreviewLoading(false))
  }

  async function startMatchingPreview() {
    if (validationBatchCount === 0 || busy) return
    setError('')
    try {
      const resolved = await resolveActionableIds()
      startPreview(resolved.ids)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  function startSelectedPreview() {
    setError('')
    if (selectedActionableIds.length === 0) {
      setError(NO_SELECTED_ACTIONABLE_MESSAGE)
      return
    }
    startPreview(selectedActionableIds)
  }

  async function confirmPreview() {
    if (previewContactIds.length === 0) return
    setIsConfirming(true)
    setPreviewError('')
    try {
      const batch = await createEmailVerificationBatch({ campaign_id: campaignId, contact_ids: previewContactIds })
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

  async function downloadValidEmails() {
    if (counts.valid === 0 || isDownloading) return
    setError('')
    setIsDownloading(true)
    try {
      await downloadFreshValidEmailCsv(campaignId)
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsDownloading(false)
    }
  }

  const bulkActions = selected.size > 0
    ? [{ label: selectedActionableIds.length > 0 ? `Validate ${selectedActionableIds.length}` : 'Validate selected', onClick: startSelectedPreview }]
    : []

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <StageViewHeader
          stageNum="S4"
          stageLabel="Email Verification"
          stageColor="var(--s5)"
          stageBg="var(--s5-bg)"
          stats={validationStats}
          primaryAction={matchingActionableCount > 0 ? {
            label: primaryValidationLabel,
            disabled: busy,
            onClick: () => { void startMatchingPreview() },
          } : undefined}
          secondaryAction={counts.failed > 0 ? {
            label: `Retry ${counts.failed} failed`,
            onClick: () => { setFilter('failed'); resetViewControls() },
          } : undefined}
        />

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="button"
            className="oc-btn oc-btn-secondary oc-btn-sm"
            disabled={counts.valid === 0 || isDownloading}
            onClick={() => { void downloadValidEmails() }}
            title="Download all fresh valid emails in this campaign"
            style={{
              opacity: counts.valid === 0 || isDownloading ? 0.55 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.375rem',
            }}
          >
            {isDownloading ? (
              <Loader2 size={13} style={{ animation: 'spin 0.7s linear infinite' }} />
            ) : (
              <IconDownload size={13} />
            )}
            Download valid emails
            {counts.valid > 0 && (
              <span style={{ color: 'var(--oc-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                {counts.valid.toLocaleString()}
              </span>
            )}
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--oc-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Company A-Z
          </span>
          <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', position: 'relative' }}>
            {['all', ...LETTERS].map((letter) => {
              const count = letter === 'all' ? letterAllTotal : (letterCounts?.counts[letter] ?? 0)
              const active = letterFilter === letter
              return (
                <button
                  key={letter}
                  type="button"
                  onClick={() => {
                    setLetterFilter(letter)
                    resetViewControls()
                  }}
                  style={{
                    padding: '0.25rem 0.5rem',
                    borderRadius: '0.375rem',
                    fontSize: '0.75rem',
                    fontWeight: active ? 700 : 500,
                    fontFamily: 'var(--font-mono)',
                    background: active ? 'var(--s5)' : 'var(--oc-surface)',
                    color: active ? '#fff' : count > 0 ? 'var(--oc-text)' : 'var(--oc-muted)',
                    border: active ? '1.5px solid var(--s5)' : '1.5px solid var(--oc-border)',
                    cursor: count > 0 || letter === 'all' ? 'pointer' : 'default',
                    opacity: count === 0 && letter !== 'all' ? 0.4 : 1,
                    minWidth: '2rem',
                    textAlign: 'center',
                  }}
                >
                  {letter}
                  {count > 0 && (
                    <span style={{ marginLeft: '0.25rem', fontWeight: 400, opacity: 0.75 }}>
                      {count > 999 ? `${Math.floor(count / 1000)}k` : count}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        <StageToolbar
          stageColor="var(--s5)"
          filters={filters}
          activeFilter={filter}
          onFilterChange={(value) => {
            setFilter(value as FilterValue)
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

        {matchingActionableCount > 0 && !busy && (
          <button
            type="button"
            onClick={() => { void selectMatchingActionable() }}
            style={{
              alignSelf: 'flex-start',
              border: 'none',
              background: 'none',
              color: 'var(--s5)',
              cursor: 'pointer',
              fontSize: '0.8125rem',
              fontWeight: 700,
              padding: '0 0.125rem',
              textDecoration: 'underline',
              textUnderlineOffset: '2px',
            }}
          >
            {allMatchingSelected
              ? matchingSelectionTotal > MAX_VERIFICATION_BATCH_SIZE
                ? `First ${MAX_VERIFICATION_BATCH_SIZE} of ${matchingSelectionTotal.toLocaleString()} matching selected`
                : `All ${matchingSelectionTotal.toLocaleString()} matching selected`
              : matchingActionableCount > MAX_VERIFICATION_BATCH_SIZE
                ? `Select first ${MAX_VERIFICATION_BATCH_SIZE} of ${matchingActionableCount.toLocaleString()} actionable`
                : `Select all ${matchingActionableCount.toLocaleString()} actionable`}
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
            Loading contacts
          </div>
        ) : rows.length === 0 ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            No selected emails match this filter.
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
              <ValidationTable
                rows={rows}
                selected={selected}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                onValidate={(id) => startPreview([id])}
                validateDisabled={busy}
              />
            </div>
            <div className="md:hidden">
              <ValidationCards
                rows={rows}
                selected={selected}
                onToggleSelect={toggleSelect}
                onValidate={(id) => startPreview([id])}
                validateDisabled={busy}
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

      <EmailVerificationPreviewDialog
        open={previewOpen}
        preview={preview}
        previewSummary={previewSummary}
        loading={previewLoading}
        error={previewError}
        isConfirming={isConfirming}
        onClose={() => { if (!isConfirming) setPreviewOpen(false) }}
        onConfirm={() => void confirmPreview()}
      />
    </>
  )
}
