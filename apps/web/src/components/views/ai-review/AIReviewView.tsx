import { useEffect, useMemo, useState } from 'react'
import { MOCK_AI_ROWS, MOCK_AI_STATS, MOCK_STATS } from '../../../lib/useAppData'
import type { AIVerdict, MockAIRow } from '../../../lib/useAppData'
import type { AiReviewLabelCounts, DomainLetterCounts, StatsResponse } from '../../../lib/types'
import { getAiReviewLabelCounts, getAiReviewLetterCounts, listAiReviewDomains } from '../../../lib/api'
import { StageViewHeader }    from '../shared/StageViewHeader'
import { AIReviewToolbar }    from './AIReviewToolbar'
import { AIReviewTable }      from './AIReviewTable'
import { AIReviewCards }      from './AIReviewCards'
import { AIReasoningDrawer }  from './AIReasoningDrawer'
import { AISettingsDrawer }   from './AISettingsDrawer'

type VerdictFilter = 'all' | AIVerdict
type AIReviewFilter = VerdictFilter | 'unclassified'
const PAGE_SIZE = 50
const LETTERS = ['#', ...Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i))]

interface AIReviewViewProps {
  stats?: StatsResponse | null
  campaignId: string
}

export function AIReviewView({ stats: rawStats, campaignId }: AIReviewViewProps) {
  const stats = rawStats ?? MOCK_STATS

  const [rows, setRows]             = useState<MockAIRow[]>(MOCK_AI_ROWS)
  const [domainTotal, setDomainTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [letterFilter, setLetterFilter] = useState<string>('all')
  const [letterCounts, setLetterCounts] = useState<DomainLetterCounts | null>(null)
  const [labelCounts, setLabelCounts] = useState<AiReviewLabelCounts | null>(null)
  const allDomainTotal = letterCounts
    ? Object.values(letterCounts.counts).reduce((sum, count) => sum + count, 0)
    : domainTotal
  const [filter, setFilter]         = useState<AIReviewFilter>('all')
  const [search, setSearch]         = useState('')
  const [selected, setSelected]     = useState<Set<string>>(new Set())
  const [reasoningRow, setReasoningRow] = useState<MockAIRow | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function toVerdict(value: string | null): AIVerdict {
    const normalized = (value ?? '').trim().toLowerCase()
    if (!normalized) return 'Unclassified'
    if (normalized === 'possible') return 'Possible'
    if (normalized === 'crap') return 'Crap'
    if (normalized === 'unknown') return 'Unknown'
    return 'Unknown'
  }

  function reasoningPreview(reasoning: Record<string, unknown> | null): string {
    if (!reasoning) return 'Ready for AI classification.'
    const summary = reasoning.summary
    if (typeof summary === 'string' && summary.trim()) return summary.trim()
    return 'Classification completed.'
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await listAiReviewDomains(campaignId, {
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          letter: letterFilter !== 'all' ? letterFilter : undefined,
          label: filter !== 'all' ? filter.toLowerCase() : undefined,
          search: search.trim() ? search.trim() : undefined,
        })
        if (cancelled) return
        const mapped: MockAIRow[] = data.items.map((item) => ({
          id: item.domain_id,
          domain: item.domain,
          url: item.normalized_url || item.raw_url,
          verdict: toVerdict(item.effective_label),
          confidence: Math.round((item.effective_confidence ?? 0) * 100),
          reasoning: reasoningPreview(item.reasoning_json),
          pagesReviewed: Array.isArray(item.evidence_json?.evidence)
            ? item.evidence_json.evidence.length
            : Array.isArray(item.evidence_json?.pages) ? item.evidence_json.pages.length : 0,
          updatedAt: item.activity_at,
        }))
        setRows(mapped)
        setDomainTotal(data.total)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load AI-decidable domains.')
        setRows([])
        setDomainTotal(0)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [campaignId, filter, letterFilter, page, search])

  useEffect(() => {
    let cancelled = false
    async function loadCounts() {
      try {
        const counts = await getAiReviewLetterCounts(campaignId)
        if (!cancelled) setLetterCounts(counts)
      } catch {
        if (!cancelled) setLetterCounts(null)
      }
    }
    void loadCounts()
    return () => {
      cancelled = true
    }
  }, [campaignId])

  useEffect(() => {
    let cancelled = false
    async function loadCounts() {
      try {
        const counts = await getAiReviewLabelCounts(campaignId, {
          letter: letterFilter !== 'all' ? letterFilter : undefined,
          search: search.trim() ? search.trim() : undefined,
        })
        if (!cancelled) setLabelCounts(counts)
      } catch {
        if (!cancelled) setLabelCounts(null)
      }
    }
    void loadCounts()
    return () => {
      cancelled = true
    }
  }, [campaignId, letterFilter, search])

  const aiStats = [
    { label: 'possible', value: labelCounts?.possible ?? rows.filter((r) => r.verdict === 'Possible').length, color: 'var(--s2)', live: (stats.analysis?.running ?? 0) > 0 },
    { label: 'unknown',  value: labelCounts?.unknown ?? rows.filter((r) => r.verdict === 'Unknown').length,  color: 'var(--oc-warn-text)' },
    { label: 'crap',     value: labelCounts?.crap ?? rows.filter((r) => r.verdict === 'Crap').length,     color: 'var(--oc-fail-text)' },
    { label: 'unclassified', value: labelCounts?.unclassified ?? stats.analysis?.queued ?? MOCK_AI_STATS.running },
  ]

  const visibleRows = useMemo(() => rows, [rows])

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (visibleRows.every((r) => selected.has(r.id))) {
      setSelected(new Set())
    } else {
      setSelected(new Set(visibleRows.map((r) => r.id)))
    }
  }

  function handleLabelChange(id: string, verdict: AIVerdict) {
    setRows((prev) => prev.map((r) => r.id === id ? { ...r, verdict } : r))
  }

  function handleBulkLabel(verdict: AIVerdict) {
    const ids = [...selected]
    setRows((prev) => prev.map((r) => ids.includes(r.id) ? { ...r, verdict } : r))
    setSelected(new Set())
  }

  const unclassifiedCount = labelCounts?.unclassified ?? 0
  const etaSecs = stats.analysis?.eta_seconds ?? null
  const totalPages = Math.ceil(domainTotal / PAGE_SIZE)

  function goToPage(nextPage: number) {
    setPage(nextPage)
    setSelected(new Set())
  }

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        <StageViewHeader
          stageNum="S2"
          stageLabel="AI Review"
          stageColor="var(--s2)"
          stageBg="var(--s2-bg)"
          stats={aiStats}
          etaSeconds={etaSecs}
          onOpenSettings={() => setSettingsOpen(true)}
          settingsLabel="Prompt"
          primaryAction={unclassifiedCount > 0 ? {
            label: `Classify ${unclassifiedCount.toLocaleString()} unclassified`,
            onClick: () => {
              setFilter('unclassified')
              setPage(0)
              setSelected(new Set())
            },
          } : {
            label: 'Classify unreviewed',
            onClick: () => console.log('Classify all'),
          }}
          secondaryAction={rows.filter((r) => r.verdict === 'Possible').length > 0 ? {
            label: `${rows.filter((r) => r.verdict === 'Possible').length} possible →`,
            onClick: () => setFilter('Possible'),
          } : undefined}
        />

        <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', position: 'relative' }}>
          {['all', ...LETTERS].map((l) => {
            const count = l === 'all' ? allDomainTotal : (letterCounts?.counts[l] ?? 0)
            const active = letterFilter === l
            return (
              <button
                key={l}
                type="button"
                onClick={() => {
                  setLetterFilter(l)
                  setPage(0)
                  setSelected(new Set())
                }}
                style={{
                  padding: '0.25rem 0.5rem', borderRadius: '0.375rem', fontSize: '0.75rem',
                  fontWeight: active ? 700 : 500, fontFamily: 'var(--font-mono)',
                  background: active ? 'var(--s2)' : 'var(--oc-surface)',
                  color: active ? '#fff' : count > 0 ? 'var(--oc-text)' : 'var(--oc-muted)',
                  border: active ? '1.5px solid var(--s2)' : '1.5px solid var(--oc-border)',
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

        <AIReviewToolbar
          rows={visibleRows}
          counts={labelCounts}
          filter={filter}
          search={search}
          selectedIds={selected}
          onFilterChange={(value) => {
            setFilter(value)
            setPage(0)
            setSelected(new Set())
          }}
          onSearchChange={(value) => {
            setSearch(value)
            setPage(0)
            setSelected(new Set())
          }}
          onClassifyAll={() => console.log('Classify all')}
          onBulkLabel={handleBulkLabel}
          onClearSelection={() => setSelected(new Set())}
        />

        {loading ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            Loading AI-decidable domains…
          </div>
        ) : error ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-fail-text)', fontSize: '0.9375rem' }}>
            {error}
          </div>
        ) : visibleRows.length === 0 ? (
          <div className="oc-panel" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
            No companies match this filter.
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <AIReviewTable
                rows={visibleRows}
                selectedIds={selected}
                onToggleRow={toggleSelect}
                onToggleAll={toggleSelectAll}
                onLabelChange={handleLabelChange}
                onViewReasoning={setReasoningRow}
              />
            </div>
            <div className="md:hidden">
              <AIReviewCards
                rows={visibleRows}
                selectedIds={selected}
                onToggleRow={toggleSelect}
                onLabelChange={handleLabelChange}
                onViewReasoning={setReasoningRow}
              />
            </div>
          </>
        )}

        {totalPages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              disabled={page === 0 || loading}
              onClick={() => goToPage(page - 1)}
              className="oc-btn oc-btn-secondary oc-btn-sm"
              style={{ opacity: page === 0 || loading ? 0.4 : 1 }}
            >
              ← Prev
            </button>
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', fontFamily: 'var(--font-mono)' }}>
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages - 1 || loading}
              onClick={() => goToPage(page + 1)}
              className="oc-btn oc-btn-secondary oc-btn-sm"
              style={{ opacity: page >= totalPages - 1 || loading ? 0.4 : 1 }}
            >
              Next →
            </button>
          </div>
        )}

      </div>

      <AIReasoningDrawer row={reasoningRow} campaignId={campaignId} onClose={() => setReasoningRow(null)} />
      <AISettingsDrawer isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} campaignId={campaignId} />
    </>
  )
}
