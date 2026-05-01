import { useCallback, useEffect, useState } from 'react'
import type { TitleMatchRuleRead, TitleRuleStatsResponse, TitleTestResult } from '../../lib/types'
import {
  createTitleMatchRule,
  deleteTitleMatchRule,
  getTitleRuleStats,
  listTitleMatchRules,
  rematchContacts,
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
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingStats, setIsLoadingStats] = useState(false)

  const [testTitleValue, setTestTitleValue] = useState('')
  const [testResult, setTestResult] = useState<TitleTestResult | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const [newRuleType, setNewRuleType] = useState<'include' | 'exclude'>('include')
  const [newMatchType, setNewMatchType] = useState<'keyword' | 'regex' | 'seniority'>('keyword')
  const [newKeywords, setNewKeywords] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const [isSeeding, setIsSeeding] = useState(false)
  const [isRematching, setIsRematching] = useState(false)
  const [rematchResult, setRematchResult] = useState<string | null>(null)
  const [deletingIds, setDeletingIds] = useState(new Set<string>())
  const [pendingDeleteRuleId, setPendingDeleteRuleId] = useState<string | null>(null)
  const [error, setError] = useState('')

  const loadStats = useCallback(async (id: string) => {
    setIsLoadingStats(true)
    try {
      setStats(await getTitleRuleStats(id))
    } catch {
      // stats failure is non-blocking — rules remain usable
    } finally {
      setIsLoadingStats(false)
    }
  }, [])

  const loadAll = useCallback(async () => {
    if (!campaignId) return
    setIsLoading(true)
    try {
      setRules(await listTitleMatchRules(campaignId))
      setError('')
    } catch {
      setError('Failed to load rules')
    } finally {
      setIsLoading(false)
    }
    void loadStats(campaignId)
  }, [campaignId, loadStats])

  useEffect(() => {
    if (isOpen) void loadAll()
  }, [isOpen, loadAll])

  const onTest = async () => {
    if (!testTitleValue.trim() || !campaignId) return
    setIsTesting(true)
    setTestResult(null)
    setError('')
    try {
      setTestResult(await testTitleMatch(campaignId, testTitleValue.trim()))
    } catch {
      setError('Test failed')
    } finally {
      setIsTesting(false)
    }
  }

  const onAddRule = async () => {
    if (!newKeywords.trim() || !campaignId) return
    setIsAdding(true)
    setError('')
    try {
      await createTitleMatchRule({ campaign_id: campaignId, rule_type: newRuleType, keywords: newKeywords.trim(), match_type: newMatchType })
      setNewKeywords('')
      await loadAll()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add rule')
    } finally {
      setIsAdding(false)
    }
  }

  const onDeleteRule = async (ruleId: string) => {
    if (!campaignId) return
    setDeletingIds((p) => new Set([...p, ruleId]))
    try {
      await deleteTitleMatchRule(ruleId, campaignId)
      await loadAll()
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

  const getMatchCount = (ruleId: string) =>
    stats?.rules.find((s) => s.rule_id === ruleId)?.contact_match_count ?? null

  const onSeedRules = async () => {
    if (!campaignId) return
    setIsSeeding(true)
    try {
      await seedTitleMatchRules(campaignId)
      await loadAll()
    } catch {
      setError('Failed to seed rules')
    } finally {
      setIsSeeding(false)
    }
  }


  const onReapply = async () => {
    if (!campaignId) return
    setIsRematching(true)
    setRematchResult(null)
    setError('')
    try {
      const res = await rematchContacts(campaignId)
      setRematchResult(`Re-applied — ${res.updated} contact flag(s) updated.`)
      await loadAll()
    } catch {
      setError('Failed to re-apply rules')
    } finally {
      setIsRematching(false)
    }
  }

  const isBusy = isAdding || isSeeding || isTesting || isRematching || deletingIds.size > 0
  const includeRules = rules.filter((r) => r.rule_type === 'include')
  const excludeRules = rules.filter((r) => r.rule_type === 'exclude')

  return (
    <Drawer isOpen={isOpen} onClose={onClose} title="Title Match Rules" subtitle="S3 · Contacts" size="lg">
      <div className="flex h-full flex-col gap-5 overflow-y-auto p-5">

        {/* Stats header */}
        {(stats || isLoadingStats) && (
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm">
            {isLoadingStats && !stats ? (
              <span className="text-emerald-600">Computing stats…</span>
            ) : stats ? (
              <>
                <span className="font-black text-emerald-800">{stats.total_matched.toLocaleString()}</span>
                <span className="text-emerald-700">
                  of {stats.total_contacts.toLocaleString()} contacts match current rules
                </span>
                {isLoadingStats && <span className="text-[10px] text-emerald-500">updating…</span>}
              </>
            ) : null}
          </div>
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
                {pendingDeleteRuleId === r.id ? (
                  <>
                    <button type="button" onClick={() => { setPendingDeleteRuleId(null); void onDeleteRule(r.id) }} disabled={isBusy}
                      className="text-[10px] font-bold text-rose-600 transition hover:text-rose-800 disabled:opacity-50">
                      {deletingIds.has(r.id) ? '…' : 'Confirm'}
                    </button>
                    <button type="button" onClick={() => setPendingDeleteRuleId(null)}
                      className="text-[10px] text-(--oc-muted) transition hover:text-(--oc-text)">
                      Cancel
                    </button>
                  </>
                ) : (
                  <button type="button" onClick={() => setPendingDeleteRuleId(r.id)} disabled={isBusy}
                    className="text-xs text-rose-400 transition hover:text-rose-600 disabled:opacity-50">
                    ✕
                  </button>
                )}
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
                {pendingDeleteRuleId === r.id ? (
                  <>
                    <button type="button" onClick={() => { setPendingDeleteRuleId(null); void onDeleteRule(r.id) }} disabled={isBusy}
                      className="text-[10px] font-bold text-rose-600 transition hover:text-rose-800 disabled:opacity-50">
                      {deletingIds.has(r.id) ? '…' : 'Confirm'}
                    </button>
                    <button type="button" onClick={() => setPendingDeleteRuleId(null)}
                      className="text-[10px] text-(--oc-muted) transition hover:text-(--oc-text)">
                      Cancel
                    </button>
                  </>
                ) : (
                  <button type="button" onClick={() => setPendingDeleteRuleId(r.id)} disabled={isBusy}
                    className="text-xs text-rose-400 transition hover:text-rose-600 disabled:opacity-50">
                    ✕
                  </button>
                )}
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
              disabled={isBusy || !newKeywords.trim()}
              className="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {isAdding ? '…' : 'Add'}
            </button>
          </div>
          <p className="mt-2 text-[10px] text-(--oc-muted)">
            Include: ALL keywords must appear (comma-separated). Regex: full pattern. Seniority: preset group. Exclude: ANY keyword disqualifies.
          </p>
        </section>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void onReapply()}
            disabled={isLoading || isBusy}
            className="rounded-xl border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-800 transition hover:bg-emerald-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isRematching ? 'Re-applying…' : 'Re-apply to contacts'}
          </button>
          <button
            type="button"
            onClick={() => void onSeedRules()}
            disabled={isLoading || isBusy}
            className="rounded-xl border border-(--oc-border) px-3 py-1.5 text-xs font-medium text-(--oc-muted) transition hover:border-emerald-400 hover:text-emerald-800 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSeeding ? 'Seeding…' : 'Seed default rules'}
          </button>
        </div>
        {rematchResult && (
          <p className="text-xs text-emerald-700">{rematchResult}</p>
        )}
      </div>
    </Drawer>
  )
}
