import { useCallback, useEffect, useState } from 'react'
import type {
  ContactCompanyListResponse,
  ContactCompanySummary,
  ContactCountsResponse,
  ContactStageFilter,
  ProspectContactRead,
  TitleMatchRuleRead,
} from '../../lib/types'
import {
  ApiError,
  createTitleMatchRule,
  deleteTitleMatchRule,
  getContactCounts,
  getContactsExportUrl,
  listCompanyContacts,
  listContactCompanies,
  listTitleMatchRules,
  seedTitleMatchRules,
  verifyContacts,
} from '../../lib/api'
import { summarizeCompanyContacts } from '../../lib/contactPreview'
import { ContactPreviewTable } from '../contacts/ContactPreviewTable'
import { Drawer } from '../ui/Drawer'
import {
  IconChevronLeft,
  IconChevronRight,
  IconDownload,
  IconPlus,
  IconRefresh,
  IconTrash,
  IconZap,
} from '../ui/icons'

const STAGE_FILTERS: Array<{ value: ContactStageFilter; label: string; countKey: keyof ContactCountsResponse }> = [
  { value: 'all', label: 'All', countKey: 'total' },
  { value: 'fetched', label: 'Fetched', countKey: 'fetched' },
  { value: 'verified', label: 'Verified', countKey: 'verified' },
  { value: 'campaign_ready', label: 'Campaign ready', countKey: 'campaign_ready' },
]

const VERIFICATION_FILTER_OPTIONS = [
  { value: '', label: 'Any verification' },
  { value: 'unverified', label: 'Unverified' },
  { value: 'valid', label: 'Valid' },
  { value: 'invalid', label: 'Invalid' },
  { value: 'catch_all', label: 'Catch-all' },
  { value: 'unknown', label: 'Unknown' },
] as const

function parseError(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === 'string') return err.detail
    return JSON.stringify(err.detail)
  }
  if (err instanceof Error) return err.message
  return 'Unknown error'
}

interface TitleRulesManagerProps {
  rules: TitleMatchRuleRead[]
  onAdd: (rule_type: 'include' | 'exclude', keywords: string) => void
  onDelete: (id: string) => void
  deletingIds: Set<string>
  onSeed: () => void
  isSeeding: boolean
  error: string
}

function TitleRulesManager({ rules, onAdd, onDelete, deletingIds, onSeed, isSeeding, error }: TitleRulesManagerProps) {
  const [newType, setNewType] = useState<'include' | 'exclude'>('include')
  const [newKeywords, setNewKeywords] = useState('')

  const includeRules = rules.filter((r) => r.rule_type === 'include')
  const excludeRules = rules.filter((r) => r.rule_type === 'exclude')

  const handleAdd = () => {
    const trimmed = newKeywords.trim()
    if (!trimmed) return
    onAdd(newType, trimmed)
    setNewKeywords('')
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-[var(--oc-text)]">
          Title Match Rules
          <span className="ml-2 font-normal text-[var(--oc-muted)]">({rules.length})</span>
        </h3>
        <button
          type="button"
          onClick={onSeed}
          disabled={isSeeding}
          className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:opacity-50"
        >
          {isSeeding ? 'Seeding…' : 'Seed Defaults'}
        </button>
      </div>

      {error && <p className="text-xs text-rose-600">{error}</p>}

      <div className="flex items-center gap-2">
        <select
          value={newType}
          onChange={(e) => setNewType(e.target.value as 'include' | 'exclude')}
          className="rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1.5 text-xs text-[var(--oc-text)]"
        >
          <option value="include">Include</option>
          <option value="exclude">Exclude</option>
        </select>
        <input
          type="text"
          value={newKeywords}
          onChange={(e) => setNewKeywords(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          placeholder={newType === 'include' ? 'e.g. marketing, director' : 'e.g. assistant'}
          className="flex-1 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs text-[var(--oc-text)] placeholder:text-[var(--oc-muted)]"
        />
        <button
          type="button"
          onClick={handleAdd}
          className="flex items-center gap-1.5 rounded-lg bg-[var(--oc-accent)] px-3 py-1.5 text-xs font-bold text-white transition hover:opacity-90"
        >
          <IconPlus size={12} />
          Add
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">
            Include ({includeRules.length})
            <span className="ml-1 font-normal normal-case">AND within rule, OR between rules</span>
          </p>
          <div className="space-y-1">
            {includeRules.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between rounded-lg border border-[var(--oc-border)] bg-[var(--oc-surface)] px-2.5 py-1.5"
              >
                <span className="text-xs text-[var(--oc-text)]">{r.keywords}</span>
                <button
                  type="button"
                  onClick={() => onDelete(r.id)}
                  disabled={deletingIds.has(r.id)}
                  aria-label={`Delete rule: ${r.keywords}`}
                  className="ml-2 text-[var(--oc-muted)] transition hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <IconTrash size={13} />
                </button>
              </div>
            ))}
            {includeRules.length === 0 && <p className="text-xs text-[var(--oc-muted)]">No include rules yet.</p>}
          </div>
        </div>
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">
            Exclude ({excludeRules.length})
            <span className="ml-1 font-normal normal-case">Any keyword disqualifies</span>
          </p>
          <div className="space-y-1">
            {excludeRules.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5"
              >
                <span className="text-xs text-rose-700">{r.keywords}</span>
                <button
                  type="button"
                  onClick={() => onDelete(r.id)}
                  disabled={deletingIds.has(r.id)}
                  aria-label={`Delete rule: ${r.keywords}`}
                  className="ml-2 text-rose-400 transition hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <IconTrash size={13} />
                </button>
              </div>
            ))}
            {excludeRules.length === 0 && <p className="text-xs text-[var(--oc-muted)]">No exclude rules yet.</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

interface CompanyDrawerProps {
  company: ContactCompanySummary
  onClose: () => void
  rules: TitleMatchRuleRead[]
  isRulesLoading: boolean
  rulesError: string
  isSeeding: boolean
  deletingRuleIds: Set<string>
  onAddRule: (rt: 'include' | 'exclude', kw: string) => void
  onDeleteRule: (id: string) => void
  onSeed: () => void
}

function CompanyDrawer({
  company,
  onClose,
  rules,
  isRulesLoading,
  rulesError,
  isSeeding,
  deletingRuleIds,
  onAddRule,
  onDeleteRule,
  onSeed,
}: CompanyDrawerProps) {
  const [contacts, setContacts] = useState<ProspectContactRead[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [matchedOnly, setMatchedOnly] = useState(false)
  const [isRulesOpen, setIsRulesOpen] = useState(false)

  useEffect(() => {
    setIsLoading(true)
    setError('')
    listCompanyContacts(company.company_id, { limit: 200 })
      .then((data) => setContacts(data.items))
      .catch((err) => setError(parseError(err)))
      .finally(() => setIsLoading(false))
  }, [company.company_id])

  const displayed = matchedOnly ? contacts.filter((c) => c.title_match) : contacts
  const summary = summarizeCompanyContacts(contacts)
  const exportUrl = getContactsExportUrl({ companyId: company.company_id })

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title={company.domain}
      subtitle="Company contacts"
      size="lg"
      headerMeta={
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-700">
            {summary.total} fetched
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-700">
            {summary.verified} verified
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-700">
            {summary.campaignReady} ready
          </span>
          <span className="text-[11px] text-[var(--oc-muted)]">
            {summary.matched} matched · {summary.withEmail} with email · {summary.eligibleToVerify} queued-to-verify
          </span>
        </div>
      }
      headerActions={
        <a
          href={exportUrl}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] no-underline transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
        >
          <IconDownload size={13} />
          Export CSV
        </a>
      }
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-[var(--oc-border)] px-4 py-2.5">
          <button
            type="button"
            onClick={() => setMatchedOnly(false)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              !matchedOnly
                ? 'bg-[var(--oc-accent)] text-white'
                : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
            }`}
          >
            All ({contacts.length})
          </button>
          <button
            type="button"
            onClick={() => setMatchedOnly(true)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              matchedOnly
                ? 'bg-emerald-600 text-white'
                : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
            }`}
          >
            Matched only ({summary.matched})
          </button>
        </div>

        <div className="flex-1 overflow-auto">
          {error && <p className="px-4 py-3 text-xs text-rose-600">{error}</p>}
          {isLoading ? (
            <div className="flex h-32 items-center justify-center">
              <p className="text-sm text-[var(--oc-muted)]">Loading contacts…</p>
            </div>
          ) : displayed.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-center">
              {matchedOnly ? (
                <div>
                  <p className="text-sm font-medium text-[var(--oc-muted)]">No title-matched contacts</p>
                  <button
                    type="button"
                    onClick={() => setMatchedOnly(false)}
                    className="mt-1 text-xs text-[var(--oc-accent-ink)] underline hover:no-underline"
                  >
                    Show all {contacts.length} contacts
                  </button>
                </div>
              ) : (
                <p className="text-sm text-[var(--oc-muted)]">No contacts for this company.</p>
              )}
            </div>
          ) : (
            <ContactPreviewTable contacts={displayed} />
          )}
        </div>

        <div className="border-t border-[var(--oc-border)]">
          <button
            type="button"
            onClick={() => setIsRulesOpen((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-[var(--oc-surface)]"
          >
            <span className="text-xs font-bold text-[var(--oc-text)]">
              Title Match Rules
              {rules.length > 0 && (
                <span className="ml-2 font-normal text-[var(--oc-muted)]">({rules.length})</span>
              )}
            </span>
            <span className="text-[10px] text-[var(--oc-muted)]">{isRulesOpen ? 'Collapse ▲' : 'Expand ▼'}</span>
          </button>
          {isRulesOpen && (
            <div className="border-t border-[var(--oc-border)] p-4">
              {isRulesLoading ? (
                <p className="text-xs text-[var(--oc-muted)]">Loading rules…</p>
              ) : (
                <TitleRulesManager
                  rules={rules}
                  onAdd={onAddRule}
                  onDelete={onDeleteRule}
                  deletingIds={deletingRuleIds}
                  onSeed={onSeed}
                  isSeeding={isSeeding}
                  error={rulesError}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </Drawer>
  )
}

function SummaryCard({
  label,
  value,
  hint,
  tone = 'slate',
}: {
  label: string
  value: number
  hint: string
  tone?: 'slate' | 'amber' | 'emerald'
}) {
  const cls =
    tone === 'amber'
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : tone === 'emerald'
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-[var(--oc-border)] bg-white text-[var(--oc-text)]'
  return (
    <div className={`rounded-2xl border px-4 py-3 ${cls}`}>
      <p className="text-[10px] font-bold uppercase tracking-widest opacity-70">{label}</p>
      <p className="mt-1 text-2xl font-black tabular-nums">{value.toLocaleString()}</p>
      <p className="mt-1 text-xs opacity-75">{hint}</p>
    </div>
  )
}

function CompanyRow({ company, onClick }: { company: ContactCompanySummary; onClick: () => void }) {
  return (
    <tr
      className="cursor-pointer border-b border-[var(--oc-border)] transition-colors hover:bg-[var(--oc-surface)]"
      onClick={onClick}
    >
      <td className="px-3 py-2.5">
        <p className="text-xs font-semibold text-[var(--oc-accent-ink)]">{company.domain}</p>
        <p className="mt-0.5 text-[11px] text-[var(--oc-muted)]">
          {company.total_count} total · {company.title_matched_count} matched · {company.email_count} with email
        </p>
      </td>
      <td className="px-3 py-2.5 text-center text-xs font-bold tabular-nums text-slate-700">
        {company.fetched_count}
      </td>
      <td className="px-3 py-2.5 text-center text-xs font-bold tabular-nums text-amber-700">
        {company.verified_count}
      </td>
      <td className="px-3 py-2.5 text-center text-xs font-bold tabular-nums text-emerald-700">
        {company.campaign_ready_count}
      </td>
      <td className="px-3 py-2.5 text-center text-xs font-bold tabular-nums">
        {company.eligible_verify_count > 0 ? (
          <span className="text-[var(--oc-text)]">{company.eligible_verify_count}</span>
        ) : (
          <span className="text-[var(--oc-muted)] opacity-40">0</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-right text-[var(--oc-muted)]">
        <span className="text-[10px]">›</span>
      </td>
    </tr>
  )
}

export function ContactsView() {
  const [companies, setCompanies] = useState<ContactCompanyListResponse | null>(null)
  const [counts, setCounts] = useState<ContactCountsResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [offset, setOffset] = useState(0)
  const [limit] = useState(50)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [stageFilter, setStageFilter] = useState<ContactStageFilter>('all')
  const [verificationFilter, setVerificationFilter] = useState('')
  const [matchedOnly, setMatchedOnly] = useState(false)
  const [isVerifying, setIsVerifying] = useState(false)

  const [selectedCompany, setSelectedCompany] = useState<ContactCompanySummary | null>(null)

  const [rules, setRules] = useState<TitleMatchRuleRead[]>([])
  const [isRulesLoading, setIsRulesLoading] = useState(false)
  const [isSeeding, setIsSeeding] = useState(false)
  const [rulesError, setRulesError] = useState('')
  const [deletingRuleIds, setDeletingRuleIds] = useState<Set<string>>(new Set())

  const loadCompanies = useCallback(
    async (
      off = 0,
      nextSearch = search,
      nextStage = stageFilter,
      nextVerification = verificationFilter,
      nextMatchedOnly = matchedOnly,
    ) => {
      setIsLoading(true)
      setError('')
      try {
        const data = await listContactCompanies({
          search: nextSearch || undefined,
          limit,
          offset: off,
          titleMatch: nextMatchedOnly ? true : undefined,
          verificationStatus: nextVerification || undefined,
          stageFilter: nextStage,
        })
        setCompanies(data)
        setOffset(off)
        setSelectedCompany((prev) => prev ? data.items.find((item) => item.company_id === prev.company_id) ?? prev : prev)
      } catch (err) {
        setError(parseError(err))
      } finally {
        setIsLoading(false)
      }
    },
    [limit, matchedOnly, search, stageFilter, verificationFilter],
  )

  const loadCounts = useCallback(async () => {
    try {
      setCounts(await getContactCounts())
    } catch { /* non-critical */ }
  }, [])

  useEffect(() => {
    void loadCompanies(0, search, stageFilter, verificationFilter, matchedOnly)
  }, [loadCompanies, matchedOnly, search, stageFilter, verificationFilter])

  useEffect(() => {
    void loadCounts()
  }, [loadCounts])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const loadRules = useCallback(async () => {
    setIsRulesLoading(true)
    try {
      setRules(await listTitleMatchRules())
      setRulesError('')
    } catch (err) {
      setRulesError(parseError(err))
    } finally {
      setIsRulesLoading(false)
    }
  }, [])

  const handleSelectCompany = (company: ContactCompanySummary) => {
    setSelectedCompany(company)
    if (rules.length === 0) void loadRules()
  }

  const handleAddRule = async (rule_type: 'include' | 'exclude', keywords: string) => {
    try {
      await createTitleMatchRule({ rule_type, keywords })
      await loadRules()
      await loadCompanies(offset)
    } catch (err) {
      setRulesError(parseError(err))
    }
  }

  const handleDeleteRule = async (id: string) => {
    if (deletingRuleIds.has(id)) return
    setDeletingRuleIds((prev) => new Set([...prev, id]))
    try {
      await deleteTitleMatchRule(id)
      setRules((r) => r.filter((rule) => rule.id !== id))
      await loadCompanies(offset)
    } catch (err) {
      setRulesError(parseError(err))
    } finally {
      setDeletingRuleIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleSeed = async () => {
    setIsSeeding(true)
    try {
      await seedTitleMatchRules()
      await loadRules()
      await loadCompanies(offset)
      setRulesError('')
    } catch (err) {
      setRulesError(parseError(err))
    } finally {
      setIsSeeding(false)
    }
  }

  const handleVerify = async () => {
    setIsVerifying(true)
    setError('')
    setNotice('')
    try {
      const result = await verifyContacts({
        title_match: matchedOnly ? true : undefined,
        verification_status: verificationFilter || undefined,
        search: search || undefined,
        stage_filter: stageFilter === 'all' ? undefined : stageFilter,
      })
      setNotice(result.message)
      await Promise.all([
        loadCompanies(0, search, stageFilter, verificationFilter, matchedOnly),
        loadCounts(),
      ])
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsVerifying(false)
    }
  }

  const exportUrl = getContactsExportUrl({
    titleMatch: matchedOnly ? true : undefined,
    verificationStatus: verificationFilter || undefined,
    stageFilter,
  })

  const filteredEligibleVerify = companies?.items.reduce((sum, item) => sum + item.eligible_verify_count, 0) ?? 0

  return (
    <div className="flex h-full flex-col gap-4 overflow-hidden p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-[var(--oc-text)]">Contacts</h2>
          <p className="text-xs text-[var(--oc-muted)]">
            Step 3 contact fetch and Step 4 ZeroBounce verification live here.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void Promise.all([loadCompanies(offset), loadCounts()])}
            disabled={isLoading}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:opacity-50"
          >
            <IconRefresh size={13} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => void handleVerify()}
            disabled={isVerifying || (!companies?.total && filteredEligibleVerify === 0)}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--oc-accent)] px-3 py-1.5 text-xs font-bold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <IconZap size={13} />
            {isVerifying ? 'Queueing…' : 'Queue ZeroBounce'}
          </button>
          <a
            href={exportUrl}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] no-underline transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
          >
            <IconDownload size={13} />
            Export CSV
          </a>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Fetched"
          value={counts?.fetched ?? 0}
          hint={`${counts?.total?.toLocaleString() ?? '0'} total contacts in the system`}
        />
        <SummaryCard
          label="Verified"
          value={counts?.verified ?? 0}
          hint="ZeroBounce checked, but not necessarily campaign-ready"
          tone="amber"
        />
        <SummaryCard
          label="Campaign Ready"
          value={counts?.campaign_ready ?? 0}
          hint="Valid email, title match, and ready for outreach"
          tone="emerald"
        />
        <SummaryCard
          label="Eligible Verify"
          value={counts?.eligible_verify ?? 0}
          hint="Matched contacts with email and no ZeroBounce result yet"
        />
      </div>

      <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') setSearch(searchInput.trim()) }}
            onBlur={() => setSearch(searchInput.trim())}
            placeholder="Search by domain…"
            className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs text-[var(--oc-text)] placeholder:text-[var(--oc-muted)]"
            style={{ minWidth: 220 }}
          />
          <select
            value={verificationFilter}
            onChange={(e) => setVerificationFilter(e.target.value)}
            className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs text-[var(--oc-text)]"
          >
            {VERIFICATION_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setMatchedOnly((value) => !value)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              matchedOnly
                ? 'bg-emerald-600 text-white'
                : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
            }`}
          >
            {matchedOnly ? 'Matched only' : 'All titles'}
          </button>
          <span className="ml-auto text-[11px] text-[var(--oc-muted)]">
            Current page has {filteredEligibleVerify.toLocaleString()} verify-eligible contacts.
          </span>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Stage</span>
          {STAGE_FILTERS.map((item) => {
            const isActive = stageFilter === item.value
            const count = counts?.[item.countKey] ?? 0
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => setStageFilter(item.value)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  isActive
                    ? 'bg-[var(--oc-accent)] text-white'
                    : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                }`}
              >
                {item.label}
                <span className={`ml-1.5 rounded px-1 text-[10px] font-semibold ${isActive ? 'bg-white/20' : 'bg-slate-100 text-slate-500'}`}>
                  {count.toLocaleString()}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {notice && <p className="text-xs text-emerald-700">{notice}</p>}
      {error && <p className="text-xs text-rose-600">{error}</p>}

      <div className="flex-1 overflow-auto rounded-2xl border border-[var(--oc-border)]">
        {isLoading && !companies ? (
          <div className="flex h-40 items-center justify-center">
            <p className="text-sm text-[var(--oc-muted)]">Loading…</p>
          </div>
        ) : companies?.items.length === 0 ? (
          <div className="flex h-40 items-center justify-center text-center">
            <div>
              <p className="text-sm font-medium text-[var(--oc-muted)]">No contacts in this filter</p>
              <p className="mt-1 text-xs text-[var(--oc-muted)]">
                Fetch contacts from `contact_ready` companies, then run ZeroBounce on the matched-email set.
              </p>
            </div>
          </div>
        ) : (
          <table className="w-full table-fixed text-left">
            <colgroup>
              <col style={{ width: '42%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '8%' }} />
            </colgroup>
            <thead className="sticky top-0 bg-[var(--oc-surface-strong)]">
              <tr className="border-b border-[var(--oc-border)]">
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Domain</th>
                <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-widest text-slate-600">Fetched</th>
                <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-widest text-amber-700">Verified</th>
                <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-widest text-emerald-700">Ready</th>
                <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Queue Verify</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {companies?.items.map((c) => (
                <CompanyRow key={c.company_id} company={c} onClick={() => handleSelectCompany(c)} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {companies && (companies.has_more || offset > 0) && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-[var(--oc-muted)]">
            {offset + 1}–{Math.min(offset + limit, companies.total)} of {companies.total.toLocaleString()}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void loadCompanies(Math.max(offset - limit, 0))}
              disabled={offset === 0 || isLoading}
              className="flex items-center gap-1 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] disabled:opacity-50"
            >
              <IconChevronLeft size={13} />
              Previous
            </button>
            <button
              type="button"
              onClick={() => void loadCompanies(offset + limit)}
              disabled={!companies.has_more || isLoading}
              className="flex items-center gap-1 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] disabled:opacity-50"
            >
              Next
              <IconChevronRight size={13} />
            </button>
          </div>
        </div>
      )}

      {selectedCompany && (
        <CompanyDrawer
          company={selectedCompany}
          onClose={() => setSelectedCompany(null)}
          rules={rules}
          isRulesLoading={isRulesLoading}
          rulesError={rulesError}
          isSeeding={isSeeding}
          deletingRuleIds={deletingRuleIds}
          onAddRule={(rt, kw) => void handleAddRule(rt, kw)}
          onDeleteRule={(id) => void handleDeleteRule(id)}
          onSeed={() => void handleSeed()}
        />
      )}
    </div>
  )
}
