import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import type { DomainRead, ScrapeBatchRead, DomainLetterCounts, ScrapeJobStatusRead } from '../../../lib/types'
import type { TableSortState } from '../../../lib/tableSort'
import {
  buildApiUrl,
  getDomainLetterCounts,
  createScrapeJob,
  getActiveBatch,
  getScrapeJobStatus,
  listDomains,
} from '../../../lib/api'
import { nextTableSort } from '../../../lib/tableSort'
import { parseApiError }         from '../../../lib/utils'
import { StageViewHeader }       from '../shared/StageViewHeader'
import { ScrapingToolbar }        from './ScrapingToolbar'
import { ScrapingTable }          from './ScrapingTable'
import { ScrapingCards }          from './ScrapingCards'
import { ScrapedContentDrawer }   from './ScrapedContentDrawer'
import { ScrapingSettingsDrawer } from './ScrapingSettingsDrawer'
import type { StatusFilter }      from './ScrapingToolbar'
import { Loader2 } from 'lucide-react'

const PAGE_SIZE = 50
const POLL_STATUS_ACTIVE_MS = 4000
const POLL_HEAVY_ACTIVE_MS = 10000
const POLL_STATUS_BG_MS = 20000
const POLL_HEAVY_BG_MS = 30000

const LETTERS = ['#', ...Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i))]
const DESC_SORT_FIELDS = new Set(['updated'])

function DomainSkeleton() {
  return (
    <div className="oc-panel" style={{ overflow: 'hidden' }}>
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          style={{
            display: 'flex', gap: '1rem', alignItems: 'center',
            padding: '0.75rem 1rem',
            borderBottom: i < 7 ? '1px solid var(--oc-border)' : 'none',
          }}
        >
          <div style={{ width: '1rem', height: '1rem', borderRadius: '0.25rem', background: 'var(--oc-border)', flexShrink: 0 }} />
          <div style={{ flex: 1, height: '0.75rem', borderRadius: '0.25rem', background: 'var(--oc-border)', maxWidth: `${55 + (i * 13) % 35}%` }} />
          <div style={{ width: '4rem', height: '0.75rem', borderRadius: '0.25rem', background: 'var(--oc-border)' }} />
        </div>
      ))}
    </div>
  )
}

interface ScrapingViewProps {
  campaignId: string
  sseUrl: string  // /v1/campaigns/{id}/events/stream
  onActiveBatchChange?: (batch: ScrapeBatchRead | null, status?: ScrapeJobStatusRead | null) => void
}

export function ScrapingView({ campaignId, sseUrl, onActiveBatchChange }: ScrapingViewProps) {
  // ── Filters / selection ──────────────────────────────────────────────────
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [letterFilter, setLetterFilter] = useState<string>('all')
  const [search, setSearch]             = useState('')
  const [sort, setSort]                 = useState<TableSortState>({ sortBy: '', sortDir: 'asc' })
  // Explicit checked domain IDs (visible-page selections)
  const [selectedIds, setSelectedIds]   = useState<Set<string>>(new Set())
  // "Select all matching" filter criteria (server-side selection)
  const [filterSelection, setFilterSelection] = useState<{ scrape_status?: string; letter?: string } | null>(null)

  // ── Data ────────────────────────────────────────────────────────────────
  const [domains, setDomains]           = useState<DomainRead[]>([])
  const [domainTotal, setDomainTotal]   = useState(0)
  const [page, setPage]                 = useState(0)
  const [letterCounts, setLetterCounts] = useState<DomainLetterCounts | null>(null)
  const [activeBatch, setActiveBatch]   = useState<ScrapeBatchRead | null>(null)
  const [activeStatus, setActiveStatus] = useState<ScrapeJobStatusRead | null>(null)
  const [loading, setLoading]           = useState(false)
  const [batchError, setBatchError]     = useState<string | null>(null)
  const [isCreatingBatch, setIsCreatingBatch] = useState(false)
  const isCreatingBatchRef = useRef(false)
  const isBatchActive = activeBatch !== null && ['queued', 'dispatching', 'running'].includes(activeBatch.state)

  // ── Drawers ─────────────────────────────────────────────────────────────
  const [viewingDomain, setViewingDomain]   = useState<DomainRead | null>(null)
  const [settingsOpen, setSettingsOpen]     = useState(false)
  const isVisibleRef = useRef<boolean>(typeof document === 'undefined' ? true : document.visibilityState === 'visible')
  const statusPollBusyRef = useRef(false)
  const heavyPollBusyRef = useRef(false)
  const activeBatchRef = useRef<ScrapeBatchRead | null>(null)
  const pageRef = useRef(0)

  useEffect(() => {
    activeBatchRef.current = activeBatch
  }, [activeBatch])

  useEffect(() => {
    pageRef.current = page
  }, [page])

  useEffect(() => {
    onActiveBatchChange?.(activeBatch, activeStatus)
  }, [activeBatch, activeStatus, onActiveBatchChange])

  useEffect(() => {
    return () => onActiveBatchChange?.(null, null)
  }, [onActiveBatchChange])

  // ── Load domain list ──────────────────────────────────────────────────────
  const loadDomains = useCallback(async (p = 0) => {
    setLoading(true)
    try {
      const result = await listDomains(campaignId, {
        limit: PAGE_SIZE,
        offset: p * PAGE_SIZE,
        scrapeStatus: statusFilter !== 'all' ? statusFilter : undefined,
        letter: letterFilter !== 'all' ? letterFilter : undefined,
        search: search.trim() ? search.trim() : undefined,
        sortBy: sort.sortBy || undefined,
        sortDir: sort.sortBy ? sort.sortDir : undefined,
      })
      setDomains(result.items)
      setDomainTotal(result.total)
    } catch {
      // keep existing data
    } finally {
      setLoading(false)
    }
  }, [campaignId, statusFilter, letterFilter, search, sort.sortBy, sort.sortDir])

  const loadLetterCounts = useCallback(async () => {
    try {
      const counts = await getDomainLetterCounts(
        campaignId,
        statusFilter !== 'all' ? statusFilter : undefined,
      )
      setLetterCounts(counts)
    } catch { /* ignore */ }
  }, [campaignId, statusFilter])

  const loadActiveBatch = useCallback(async (): Promise<ScrapeBatchRead | null> => {
    try {
      const batch = await getActiveBatch(campaignId)
      setActiveBatch((prev) => {
        if (!prev && !batch) return prev
        if (!prev || !batch) return batch
        if (
          prev.id === batch.id &&
          prev.state === batch.state &&
          prev.queued_count === batch.queued_count &&
          prev.success_count === batch.success_count &&
          prev.failed_count === batch.failed_count &&
          prev.selected_domain_count === batch.selected_domain_count &&
          prev.eta_seconds === batch.eta_seconds
        ) {
          return prev
        }
        return batch
      })
      return batch
    } catch { /* ignore */ }
    return null
  }, [campaignId])

  const loadActiveStatus = useCallback(async (): Promise<ScrapeJobStatusRead | null> => {
    if (!activeBatch) {
      setActiveStatus(null)
      return null
    }
    try {
      const status = await getScrapeJobStatus(activeBatch.id)
      setActiveStatus(status)
      if (['completed', 'failed', 'inconsistent'].includes(status.state)) {
        setActiveBatch(null)
        void loadDomains(pageRef.current)
        void loadLetterCounts()
      }
      return status
    } catch {
      return null
    }
  }, [activeBatch, loadDomains, loadLetterCounts, page])

  useEffect(() => {
    void loadDomains(page)
  }, [loadDomains, page])

  useEffect(() => {
    void loadLetterCounts()
  }, [loadLetterCounts])

  useEffect(() => {
    void loadActiveBatch()
  }, [loadActiveBatch])

  useEffect(() => {
    setPage(0)
    setSelectedIds(new Set())
    setFilterSelection(null)
    setActiveStatus(null)
  }, [campaignId, statusFilter, letterFilter, search])

  // ── Visibility tracking ──────────────────────────────────────────────────
  useEffect(() => {
    if (typeof document === 'undefined') return
    const onVisibilityChange = () => {
      const wasVisible = isVisibleRef.current
      isVisibleRef.current = document.visibilityState === 'visible'
      if (!wasVisible && isVisibleRef.current) {
        void loadActiveBatch()
        void loadActiveStatus()
        void Promise.all([loadDomains(pageRef.current), loadLetterCounts()])
      }
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [loadActiveBatch, loadActiveStatus, loadDomains, loadLetterCounts])

  // ── Unified polling coordinator for S1 ──────────────────────────────────
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
      if (!isBatchActive && !isCreatingBatch) {
        scheduleHeavy(heavyInterval())
        return
      }
      heavyPollBusyRef.current = true
      try {
        await Promise.all([loadDomains(pageRef.current), loadLetterCounts()])
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
      if (!isBatchActive && !isCreatingBatch) {
        scheduleStatus(statusInterval())
        return
      }
      statusPollBusyRef.current = true
      try {
        const currentBatch = activeBatchRef.current
        if (currentBatch) {
          const status = await getScrapeJobStatus(currentBatch.id).catch(() => null)
          if (status) {
            setActiveStatus(status)
            if (['completed', 'failed', 'inconsistent'].includes(status.state)) {
              setActiveBatch(null)
              setActiveStatus((prev) => prev ?? status)
              await Promise.all([loadDomains(pageRef.current), loadLetterCounts()])
            }
          }
          return
        }

        const discovered = await getActiveBatch(campaignId).catch(() => null)
        setActiveBatch(discovered)
        if (!discovered || ['completed', 'failed'].includes(discovered.state)) {
          setActiveBatch(null)
          setActiveStatus(null)
          await Promise.all([loadDomains(pageRef.current), loadLetterCounts()])
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
  }, [campaignId, isBatchActive, isCreatingBatch, loadDomains, loadLetterCounts])

  // ── SSE nudge — scrape_batch updates ────────────────────────────────────
  const sseRef = useRef<EventSource | null>(null)
  useEffect(() => {
    const es = new EventSource(buildApiUrl(sseUrl))
    sseRef.current = es
    es.onmessage = (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data as string) as Record<string, unknown>
        if (payload.event_type === 'scrape_batch') {
          const updated: ScrapeBatchRead = {
            id: String(payload.batch_id ?? ''),
            campaign_id: String(payload.campaign_id ?? ''),
            state: String(payload.state ?? ''),
            selected_domain_count: Number(payload.selected_domain_count ?? 0),
            success_count: Number(payload.success_count ?? 0),
            failed_count: Number(payload.failed_count ?? 0),
            queued_count: Number(payload.queued_count ?? 0),
            created_at: '',
            finished_at: payload.finished_at ? String(payload.finished_at) : null,
            eta_seconds: null,
          }
          setActiveBatch((prev) => {
            if (['completed', 'failed'].includes(updated.state)) {
              // batch done — reload domain list to reflect new statuses
              void loadDomains(pageRef.current)
              void loadLetterCounts()
              return null
            }
            return prev?.id === updated.id ? updated : prev ?? updated
          })
        }
      } catch { /* ignore bad payloads */ }
    }
    return () => { es.close(); sseRef.current = null }
  }, [sseUrl, loadDomains, loadLetterCounts])

  // ── Pagination ───────────────────────────────────────────────────────────
  const totalPages = Math.ceil(domainTotal / PAGE_SIZE)

  function goToPage(p: number) {
    setPage(p)
  }

  function handleSort(field: string) {
    setSort((current) => nextTableSort(
      current,
      field,
      DESC_SORT_FIELDS.has(field) ? 'desc' : 'asc',
    ))
    setPage(0)
  }

  // ── Selection helpers ────────────────────────────────────────────────────
  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    const allVisible = domains.every((d) => selectedIds.has(d.id))
    if (allVisible) {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        domains.forEach((d) => next.delete(d.id))
        return next
      })
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        domains.forEach((d) => next.add(d.id))
        return next
      })
    }
  }

  function handleSelectAllMatching() {
    // Adds current filter criteria as a server-side selection
    const criteria: { scrape_status?: string; letter?: string } = {}
    if (statusFilter !== 'all') criteria.scrape_status = statusFilter
    if (letterFilter !== 'all') criteria.letter = letterFilter
    setFilterSelection(criteria)
    // Count: total matching (domainTotal) shown in toolbar
  }

  function clearSelection() {
    setSelectedIds(new Set())
    setFilterSelection(null)
  }

  // ── Batch creation ────────────────────────────────────────────────────────
  async function handleScrape(
    overrideFilter?: { scrape_status?: string },
    overrideDomainIds?: string[],
  ) {
    if (isCreatingBatchRef.current || isBatchActive) return
    isCreatingBatchRef.current = true
    setIsCreatingBatch(true)
    setBatchError(null)
    try {
      const body: { campaign_id: string; domain_ids?: string[]; filter?: Record<string, string | undefined> } = {
        campaign_id: campaignId,
      }
      if (overrideDomainIds && overrideDomainIds.length > 0) {
        body.domain_ids = overrideDomainIds
      } else if (overrideFilter) {
        body.filter = overrideFilter
      } else {
        const ids = [...selectedIds]
        if (ids.length > 0) body.domain_ids = ids
        if (filterSelection && Object.keys(filterSelection).length > 0) body.filter = filterSelection
      }
      const batch = await createScrapeJob(body as Parameters<typeof createScrapeJob>[0])
      setActiveBatch(batch)
      const status = await getScrapeJobStatus(batch.id).catch(() => null)
      setActiveStatus(status)
      clearSelection()
      // Reload domains to reflect queued status
      void loadDomains(page)
      void loadLetterCounts()
    } catch (err: unknown) {
      const msg = parseApiError(err)
      setBatchError(msg)
    } finally {
      isCreatingBatchRef.current = false
      setIsCreatingBatch(false)
    }
  }

  // ── Stats ─────────────────────────────────────────────────────────────────
  const statusCounts = useMemo(() => {
    if (activeStatus) {
      return {
        pending: 0,
        running: Math.max(0, activeStatus.queued + activeStatus.running),
        done: activeStatus.terminal,
        failed: activeStatus.failed,
      }
    }
    return {
      pending: 0,
      running: activeBatch
        ? activeBatch.selected_domain_count - activeBatch.success_count - activeBatch.failed_count
        : 0,
      done: 0,
      failed: 0,
    }
  }, [activeBatch, activeStatus])

  const scrapeStats = [
    { label: 'total',   value: domainTotal },
    { label: 'running', value: statusCounts.running, live: statusCounts.running > 0, color: 'var(--s1)' },
  ]

  const isScrapeLocked = isBatchActive || isCreatingBatch

  // Selected count = explicit IDs + all matching (if filter selection set)
  const effectiveSelectedCount = filterSelection ? domainTotal : selectedIds.size

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <StageViewHeader
          stageNum="S1"
          stageLabel="Scraping"
          stageColor="var(--s1)"
          stageBg="var(--s1-bg)"
          stats={scrapeStats}
          etaSeconds={activeStatus?.eta_seconds ?? activeBatch?.eta_seconds ?? null}
          onOpenSettings={() => setSettingsOpen(true)}
          settingsLabel="Rules"
          primaryAction={!isBatchActive ? {
            label: isCreatingBatch ? 'Creating batch...' : `Scrape ${domainTotal.toLocaleString()} pending`,
            onClick: () => void handleScrape({ scrape_status: 'pending' }),
            disabled: isCreatingBatch,
          } : undefined}
          secondaryAction={!isBatchActive ? {
            label: isCreatingBatch ? 'Creating...' : 'Retry failed',
            onClick: () => void handleScrape({ scrape_status: 'failed' }),
            disabled: isCreatingBatch,
          } : undefined}
        />

        {isCreatingBatch && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '0.75rem',
            padding: '0.75rem 1rem', borderRadius: '0.625rem',
            background: 'color-mix(in srgb, var(--s1-bg) 70%, white)',
            border: '1px solid color-mix(in srgb, var(--s1) 28%, transparent)',
          }}>
            <Loader2 size={14} strokeWidth={2.5} style={{ animation: 'spin 0.9s linear infinite', flexShrink: 0, color: 'var(--s1)' }} />
            <span style={{ fontSize: '0.875rem', fontWeight: 650, color: 'var(--s1)' }}>
              Creating scrape batch... actions are locked until the request returns.
            </span>
          </div>
        )}

        {/* Active batch progress banner */}
        {isBatchActive && activeBatch && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '0.75rem',
            padding: '0.75rem 1rem', borderRadius: '0.625rem',
            background: 'var(--s1-bg)', border: '1px solid color-mix(in srgb, var(--s1) 30%, transparent)',
          }}>
            <Loader2 size={14} strokeWidth={2.5} style={{ animation: 'spin 0.9s linear infinite', flexShrink: 0, color: 'var(--s1)' }} />
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--s1)' }}>
              Scraping in progress —{' '}
              <span style={{ fontFamily: 'var(--font-mono)' }}>
                {activeStatus?.terminal ?? (activeBatch.success_count + activeBatch.failed_count)}
              </span>
              {' '}/ {(activeStatus?.selected ?? activeBatch.selected_domain_count).toLocaleString()} done
              {(activeStatus?.eta_seconds ?? activeBatch.eta_seconds) != null && (
                <span style={{ fontWeight: 400, color: 'var(--oc-muted)' }}>
                  {' '}· ~{Math.ceil(((activeStatus?.eta_seconds ?? activeBatch.eta_seconds) ?? 0) / 60)}m remaining
                </span>
              )}
              {activeStatus?.state === 'inconsistent' && (
                <span style={{ fontWeight: 500, color: 'var(--oc-fail-text)' }}>
                  {' '}· queue state needs reconciliation
                </span>
              )}
            </span>
          </div>
        )}

        {batchError && (
          <div style={{ padding: '0.75rem 1rem', borderRadius: '0.5rem', background: 'var(--oc-fail-bg)', color: 'var(--oc-fail-text)', fontSize: '0.875rem' }}>
            {batchError}
          </div>
        )}

        {/* Letter pills */}
        <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', position: 'relative' }}>
          {['all', ...LETTERS].map((l) => {
            const count = l === 'all' ? domainTotal : (letterCounts?.counts[l] ?? 0)
            const active = letterFilter === l
            return (
              <button
                key={l}
                type="button"
                onClick={() => { setLetterFilter(l); setPage(0) }}
                style={{
                  padding: '0.25rem 0.5rem', borderRadius: '0.375rem', fontSize: '0.75rem',
                  fontWeight: active ? 700 : 500, fontFamily: 'var(--font-mono)',
                  background: active ? 'var(--s1)' : 'var(--oc-surface)',
                  color: active ? '#fff' : count > 0 ? 'var(--oc-text)' : 'var(--oc-muted)',
                  border: active ? '1.5px solid var(--s1)' : '1.5px solid var(--oc-border)',
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

        <ScrapingToolbar
          statusFilter={statusFilter}
          search={search}
          onStatusFilterChange={(f) => { setStatusFilter(f); setPage(0) }}
          onSearchChange={(s) => { setSearch(s); setPage(0) }}
          selectedCount={effectiveSelectedCount}
          hasFilterSelection={filterSelection !== null}
          onScrapeSelected={() => void handleScrape()}
          onSelectAllMatching={handleSelectAllMatching}
          onClearSelection={clearSelection}
          isBatchActive={isScrapeLocked}
          totalMatchingCount={domainTotal}
        />

        {loading && domains.length === 0 ? (
          <DomainSkeleton />
        ) : domains.length === 0 ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            No domains match this filter.
          </div>
        ) : (
          <div style={{ position: 'relative' }}>
            {loading && (
              <div style={{
                position: 'absolute', inset: 0, zIndex: 10,
                background: 'color-mix(in srgb, var(--oc-bg) 60%, transparent)',
                borderRadius: '0.625rem',
                display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
                paddingTop: '3rem',
              }}>
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', fontStyle: 'italic' }}>Loading…</span>
              </div>
            )}
            <div className="hidden md:block">
              <ScrapingTable
                rows={domains}
                selected={selectedIds}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                onScrapeOne={(d) => void handleScrape(undefined, [d.id])}
                onViewContent={setViewingDomain}
                sortBy={sort.sortBy}
                sortDir={sort.sortDir}
                onSort={handleSort}
                isScrapeDisabled={isScrapeLocked}
                hasActiveFilter={statusFilter !== 'all' || letterFilter !== 'all' || !!search}
                onClearFilter={() => { setStatusFilter('all'); setLetterFilter('all'); setSearch('') }}
              />
            </div>
            <div className="md:hidden">
              <ScrapingCards
                rows={domains}
                selected={selectedIds}
                onToggleSelect={toggleSelect}
                onScrapeOne={(d) => void handleScrape(undefined, [d.id])}
                onViewContent={setViewingDomain}
                isScrapeDisabled={isScrapeLocked}
              />
            </div>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              disabled={page === 0}
              onClick={() => goToPage(page - 1)}
              className="oc-btn oc-btn-secondary oc-btn-sm"
              style={{ opacity: page === 0 ? 0.4 : 1 }}
            >← Prev</button>
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', fontFamily: 'var(--font-mono)' }}>
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages - 1}
              onClick={() => goToPage(page + 1)}
              className="oc-btn oc-btn-secondary oc-btn-sm"
              style={{ opacity: page >= totalPages - 1 ? 0.4 : 1 }}
            >Next →</button>
          </div>
        )}

      </div>

      <ScrapedContentDrawer domain={viewingDomain} onClose={() => setViewingDomain(null)} />
      <ScrapingSettingsDrawer
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        campaignId={campaignId}
      />
    </>
  )
}
