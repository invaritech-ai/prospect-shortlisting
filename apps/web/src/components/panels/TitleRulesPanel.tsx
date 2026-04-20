import { useCallback, useEffect, useRef, useState } from 'react'
import type { TitleMatchRuleRead, TitleRuleImpactPreview, TitleRuleStatsResponse, TitleTestResult } from '../../lib/types'
import {
  createTitleMatchRule,
  deleteTitleMatchRule,
  getTitleRuleStats,
  listTitleMatchRules,
  previewTitleRuleImpact,
  queueTitleRuleImpactFetch,
  seedTitleMatchRules,
  testTitleMatch,
} from '../../lib/api'
import { Drawer } from '../ui/Drawer'

interface TitleRulesPanelProps {
  campaignId: string | null
  isOpen: boolean
  onClose: () => void
}

export function TitleRulesPanel({ campaignId, isOpen, onClose }: TitleRulesPanelProps) {
  const [rules, setRules] = useState<TitleMatchRuleRead[]>([])
  const [stats, setStats] = useState<TitleRuleStatsResponse | null>(null)
  const [impactPreview, setImpactPreview] = useState<TitleRuleImpactPreview | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isQueueingImpactFetch, setIsQueueingImpactFetch] = useState(false)
  const [impactSource, setImpactSource] = useState<'snov' | 'apollo' | 'both'>('snov')
  const [includeStaleImpact, setIncludeStaleImpact] = useState(false)
  const [useProviderDefaultStaleDays, setUseProviderDefaultStaleDays] = useState(true)
  const [staleDays, setStaleDays] = useState(30)
  const [forceRefreshImpact, setForceRefreshImpact] = useState(false)

  const [testTitleValue, setTestTitleValue] = useState('')
  const [testResult, setTestResult] = useState<TitleTestResult | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const [newRuleType, setNewRuleType] = useState<'include' | 'exclude'>('include')
  const [newMatchType, setNewMatchType] = useState<'keyword' | 'regex' | 'seniority'>('keyword')
  const [newKeywords, setNewKeywords] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [impactNotice, setImpactNotice] = useState('')
  const [deletingIds, setDeletingIds] = useState(new Set<string>())
  const [error, setError] = useState('')
  const impactRequestRef = useRef(0)
  const impactSourceRef = useRef(impactSource)
  const includeStaleRef = useRef(includeStaleImpact)
  const useProviderDefaultsRef = useRef(useProviderDefaultStaleDays)
  const staleDaysRef = useRef(staleDays)
  const forceRefreshRef = useRef(forceRefreshImpact)

  useEffect(() => {
    impactSourceRef.current = impactSource
  }, [impactSource])

  useEffect(() => {
    includeStaleRef.current = includeStaleImpact
  }, [includeStaleImpact])

  useEffect(() => {
    useProviderDefaultsRef.current = useProviderDefaultStaleDays
  }, [useProviderDefaultStaleDays])

  useEffect(() => {
    staleDaysRef.current = staleDays
  }, [staleDays])

  useEffect(() => {
    forceRefreshRef.current = forceRefreshImpact
  }, [forceRefreshImpact])

  const loadImpactPreview = useCallback(async () => {
    if (!campaignId) {
      impactRequestRef.current += 1
      setImpactPreview(null)
      return
    }
    const activeSource = impactSourceRef.current
    const activeIncludeStale = includeStaleRef.current
    const activeUseProviderDefaults = useProviderDefaultsRef.current
    const activeStaleDays = staleDaysRef.current
    const activeForceRefresh = forceRefreshRef.current
    const reqId = impactRequestRef.current + 1
    impactRequestRef.current = reqId
    try {
      const preview = await previewTitleRuleImpact(campaignId, {
        source: activeSource,
        includeStale: activeIncludeStale,
        ...(activeIncludeStale && !activeUseProviderDefaults ? { staleDays: activeStaleDays } : {}),
        forceRefresh: activeForceRefresh,
      })
      if (impactRequestRef.current === reqId) {
        setImpactPreview(preview)
      }
    } catch {
      if (impactRequestRef.current === reqId) {
        setImpactPreview(null)
      }
    }
  }, [campaignId])

  const loadAll = useCallback(async () => {
    setIsLoading(true)
    try {
      const [rulesData, statsData] = await Promise.all([listTitleMatchRules(), getTitleRuleStats()])
      setRules(rulesData)
      setStats(statsData)
      setError('')
    } catch {
      setError('Failed to load rules')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isOpen) void loadAll()
  }, [isOpen, loadAll])

  useEffect(() => {
    if (!isOpen) return
    void loadImpactPreview()
  }, [isOpen, campaignId, impactSource, includeStaleImpact, useProviderDefaultStaleDays, staleDays, forceRefreshImpact, loadImpactPreview])

  useEffect(() => {
    setImpactNotice('')
    if (!isOpen) {
      impactRequestRef.current += 1
      setImpactPreview(null)
    }
  }, [campaignId, isOpen])

  const onTest = async () => {
    if (!testTitleValue.trim()) return
    setIsTesting(true)
    setTestResult(null)
    try {
      setTestResult(await testTitleMatch(testTitleValue.trim()))
    } catch {
      setError('Test failed')
    } finally {
      setIsTesting(false)
    }
  }

  const onAddRule = async () => {
    if (!newKeywords.trim()) return
    setIsAdding(true)
    setError('')
    setImpactNotice('')
    try {
      await createTitleMatchRule({ rule_type: newRuleType, keywords: newKeywords.trim(), match_type: newMatchType })
      setNewKeywords('')
      await loadAll()
      await loadImpactPreview()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add rule')
    } finally {
      setIsAdding(false)
    }
  }

  const onDeleteRule = async (ruleId: string) => {
    setDeletingIds((p) => new Set([...p, ruleId]))
    setImpactNotice('')
    try {
      await deleteTitleMatchRule(ruleId)
      await loadAll()
      await loadImpactPreview()
    } catch {
      setError('Failed to delete')
    } finally {
      setDeletingIds((p) => {
        const n = new Set(p)
        n.delete(ruleId)
        return n
      })
    }
  }

  const onQueueImpactFetch = async () => {
    if (!campaignId) {
      setError('Select a campaign to queue impacted contact fetches.')
      return
    }
    setIsQueueingImpactFetch(true)
    setError('')
    setImpactNotice('')
    try {
      const result = await queueTitleRuleImpactFetch(campaignId, impactSource, {
        includeStale: includeStaleImpact,
        ...(includeStaleImpact && !useProviderDefaultStaleDays ? { staleDays } : {}),
        forceRefresh: forceRefreshImpact,
      })
      await loadImpactPreview()
      setImpactNotice(
        result.queued_count > 0
          ? `Queued ${result.queued_count.toLocaleString()} impacted company fetch jobs.`
          : 'No impacted companies needed new fetch jobs.',
      )
    } catch {
      setError('Failed to queue impacted fetch jobs')
    } finally {
      setIsQueueingImpactFetch(false)
    }
  }

  const getMatchCount = (ruleId: string) =>
    stats?.rules.find((s) => s.rule_id === ruleId)?.contact_match_count ?? null
  const onSeedRules = async () => {
    try {
      await seedTitleMatchRules()
      await loadAll()
      await loadImpactPreview()
    } catch {
      setError('Failed to seed rules')
    }
  }


  const includeRules = rules.filter((r) => r.rule_type === 'include')
  const excludeRules = rules.filter((r) => r.rule_type === 'exclude')

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Title Match Rules" subtitle="S3 · Contacts" size="lg">
      <div className="flex h-full flex-col gap-5 overflow-y-auto p-5">

        {/* Stats header */}
        {stats && (
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm">
            <span className="font-black text-emerald-800">{stats.total_matched.toLocaleString()}</span>
            <span className="text-emerald-700">
              of {stats.total_contacts.toLocaleString()} contacts match current rules
            </span>
          </div>
        )}

        {impactPreview && (
          <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-xs text-sky-800">
            <p className="font-semibold">
              Impact preview: {impactPreview.affected_company_count.toLocaleString()} companies and{' '}
              {impactPreview.affected_contact_count.toLocaleString()} matched contacts
              {forceRefreshImpact
                ? ' will be refreshed explicitly.'
                : includeStaleImpact
                  ? ' need refresh or email completion.'
                  : ' are missing email.'}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px]">
              <label className="flex items-center gap-1.5">
                source
                <select
                  value={impactSource}
                  onChange={(e) => setImpactSource(e.target.value as 'snov' | 'apollo' | 'both')}
                  className="rounded border border-sky-300 bg-white px-1.5 py-0.5 text-[11px]"
                >
                  <option value="snov">Snov</option>
                  <option value="apollo">Apollo</option>
                  <option value="both">Both</option>
                </select>
              </label>
              {impactSource === 'both' && (
                <span className="rounded border border-sky-300 bg-white px-2 py-0.5 text-[11px] font-medium text-sky-800">
                  Both runs sequentially: Snov first, Apollo follow-up per company.
                </span>
              )}
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={includeStaleImpact}
                  onChange={(e) => setIncludeStaleImpact(e.target.checked)}
                />
                Include stale contacts
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={useProviderDefaultStaleDays}
                  onChange={(e) => setUseProviderDefaultStaleDays(e.target.checked)}
                  disabled={!includeStaleImpact}
                />
                Use provider default stale days
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={forceRefreshImpact}
                  onChange={(e) => setForceRefreshImpact(e.target.checked)}
                />
                Force refresh matched contacts
              </label>
              <label className="flex items-center gap-1.5">
                stale after
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={staleDays}
                  onChange={(e) => setStaleDays(Math.max(1, Math.min(365, Number(e.target.value) || 30)))}
                  className="w-16 rounded border border-sky-300 bg-white px-1.5 py-0.5 text-[11px]"
                  disabled={!includeStaleImpact || useProviderDefaultStaleDays}
                />
                days
              </label>
              {includeStaleImpact && (
                <span className="text-sky-700">
                  stale contacts included: {impactPreview.stale_contact_count.toLocaleString()}
                </span>
              )}
              {includeStaleImpact && useProviderDefaultStaleDays && impactPreview.provider_default_days && (
                <span className="text-sky-700">
                  defaults: snov {impactPreview.provider_default_days.snov ?? 30}d, apollo {impactPreview.provider_default_days.apollo ?? 45}d
                </span>
              )}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <button
                type="button"
                onClick={() => void onQueueImpactFetch()}
                disabled={isQueueingImpactFetch || impactPreview.affected_company_count === 0 || !campaignId}
                className="rounded-lg bg-sky-600 px-3 py-1.5 text-[11px] font-bold text-white transition hover:bg-sky-700 disabled:opacity-50"
              >
                {isQueueingImpactFetch ? 'Queueing…' : 'Queue fetch for impacted companies'}
              </button>
              {!campaignId && <span className="text-[11px] text-sky-700">Select a campaign to queue jobs.</span>}
            </div>
          </div>
        )}

        {impactNotice && (
          <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
            {impactNotice}
          </p>
        )}

        {/* Test a title */}
        <section>
          <h3 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">
            Test a Title
          </h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={testTitleValue}
              onChange={(e) => setTestTitleValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void onTest()}
              placeholder="VP of Marketing"
              className="flex-1 rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/20"
            />
            <button
              type="button"
              onClick={() => void onTest()}
              disabled={isTesting || !testTitleValue.trim()}
              className="rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800 transition hover:bg-emerald-100 disabled:opacity-50"
            >
              {isTesting ? '…' : 'Test'}
            </button>
          </div>
          {testResult && (
            <div
              className={`mt-2 rounded-xl border p-3 text-xs ${
                testResult.matched
                  ? 'border-emerald-200 bg-emerald-50'
                  : 'border-rose-200 bg-rose-50'
              }`}
            >
              <p className={`font-bold ${testResult.matched ? 'text-emerald-800' : 'text-rose-700'}`}>
                {testResult.matched ? '✓ Matched' : '✗ Not matched'}
              </p>
              <p className="mt-0.5 font-mono text-[10px] text-(--oc-muted)">{testResult.normalized_title}</p>
              {testResult.matching_rules.length > 0 && (
                <p className="mt-1 text-emerald-700">
                  Rules: {testResult.matching_rules.join(', ')}
                </p>
              )}
              {testResult.excluded_by.length > 0 && (
                <p className="mt-1 text-rose-700">
                  Excluded by: {testResult.excluded_by.join(', ')}
                </p>
              )}
            </div>
          )}
        </section>

        {error && (
          <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {error}
          </p>
        )}

        {/* Include rules */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">
              Include ({includeRules.length})
            </h3>
            <p className="text-[10px] text-(--oc-muted)">AND within rule · OR between rules</p>
          </div>
          <div className="space-y-1">
            {isLoading && includeRules.length === 0 && (
              <p className="text-xs text-(--oc-muted)">Loading…</p>
            )}
            {!isLoading && includeRules.length === 0 && (
              <p className="text-xs text-(--oc-muted)">No include rules.</p>
            )}
            {includeRules.map((r) => (
              <div
                key={r.id}
                className="flex items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-1.5"
              >
                <span className="flex-1 text-xs text-emerald-900">{r.keywords}</span>
                {r.match_type !== 'keyword' && (
                  <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[9px] font-bold uppercase text-slate-600">
                    {r.match_type}
                  </span>
                )}
                {getMatchCount(r.id) !== null && (
                  <span className="rounded-full bg-emerald-200 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                    {getMatchCount(r.id)}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => void onDeleteRule(r.id)}
                  disabled={deletingIds.has(r.id)}
                  className="text-xs text-rose-400 transition hover:text-rose-600 disabled:opacity-50"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* Exclude rules */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">
              Exclude ({excludeRules.length})
            </h3>
            <p className="text-[10px] text-(--oc-muted)">Any keyword disqualifies</p>
          </div>
          <div className="space-y-1">
            {excludeRules.map((r) => (
              <div
                key={r.id}
                className="flex items-center gap-2 rounded-xl border border-rose-100 bg-rose-50 px-3 py-1.5"
              >
                <span className="flex-1 text-xs text-rose-900">{r.keywords}</span>
                {getMatchCount(r.id) !== null && (
                  <span className="rounded-full bg-rose-200 px-2 py-0.5 text-[10px] font-bold text-rose-800">
                    {getMatchCount(r.id)} blocked
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => void onDeleteRule(r.id)}
                  disabled={deletingIds.has(r.id)}
                  className="text-xs text-rose-400 transition hover:text-rose-600 disabled:opacity-50"
                >
                  ✕
                </button>
              </div>
            ))}
            {excludeRules.length === 0 && !isLoading && (
              <p className="text-xs text-(--oc-muted)">No exclude rules.</p>
            )}
          </div>
        </section>

        {/* Add rule */}
        <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
          <h3 className="mb-3 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">
            Add Rule
          </h3>
          <div className="flex flex-wrap gap-2">
            <select
              value={newRuleType}
              onChange={(e) => setNewRuleType(e.target.value as 'include' | 'exclude')}
              className="rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-xs outline-none"
            >
              <option value="include">Include</option>
              <option value="exclude">Exclude</option>
            </select>
            {newRuleType === 'include' && (
              <select
                value={newMatchType}
                onChange={(e) => { setNewMatchType(e.target.value as 'keyword' | 'regex' | 'seniority'); setNewKeywords('') }}
                className="rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-xs outline-none"
              >
                <option value="keyword">Keyword</option>
                <option value="regex">Regex</option>
                <option value="seniority">Seniority Preset</option>
              </select>
            )}
            {newMatchType === 'seniority' && newRuleType === 'include' ? (
              <select
                value={newKeywords}
                onChange={(e) => setNewKeywords(e.target.value)}
                className="flex-1 rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-xs outline-none"
              >
                <option value="">Select preset…</option>
                <option value="c_level">C-Level (CEO, CMO, CTO, COO…)</option>
                <option value="vp_level">VP Level (VP, SVP, EVP…)</option>
                <option value="director_level">Director Level</option>
                <option value="manager_level">Manager Level</option>
                <option value="senior_ic">Senior IC (Senior, Lead, Principal)</option>
              </select>
            ) : (
              <input
                type="text"
                value={newKeywords}
                onChange={(e) => setNewKeywords(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && void onAddRule()}
                placeholder={
                  newMatchType === 'regex'
                    ? String.raw`^(head|vp).*(marketing)`
                    : newRuleType === 'include'
                      ? 'marketing, director'
                      : 'assistant'
                }
                className="flex-1 rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-xs outline-none transition focus:border-emerald-400"
              />
            )}
            <button
              type="button"
              onClick={() => void onAddRule()}
              disabled={isAdding || !newKeywords.trim()}
              className="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {isAdding ? '…' : 'Add'}
            </button>
          </div>
          <p className="mt-2 text-[10px] text-(--oc-muted)">
            Include: ALL keywords must appear (comma-separated). Regex: full pattern. Seniority: preset group. Exclude: ANY keyword disqualifies.
          </p>
        </section>

        <button
          type="button"
          onClick={() => void onSeedRules()}
          className="self-start rounded-xl border border-(--oc-border) px-3 py-1.5 text-xs font-medium text-(--oc-muted) transition hover:border-emerald-400 hover:text-emerald-800"
        >
          Seed default rules
        </button>
      </div>
    </Drawer>
  )
}
