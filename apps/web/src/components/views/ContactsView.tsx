import { useCallback, useEffect, useState } from 'react'
import type {
  ContactCompanyListResponse,
  ContactCompanySummary,
  ProspectContactRead,
  TitleMatchRuleRead,
} from '../../lib/types'
import {
  createTitleMatchRule,
  deleteTitleMatchRule,
  getContactsExportUrl,
  listCompanyContacts,
  listContactCompanies,
  listTitleMatchRules,
  seedTitleMatchRules,
} from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import {
  IconChevronLeft,
  IconChevronRight,
  IconDownload,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '../ui/icons'

// ── Email status badge ────────────────────────────────────────────────────────

function EmailStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    valid:     { label: 'Valid',    cls: 'bg-emerald-100 text-emerald-700' },
    not_valid: { label: 'Invalid',  cls: 'bg-rose-100 text-rose-700' },
    unknown:   { label: 'Unknown',  cls: 'bg-slate-100 text-slate-500' },
  }
  const { label, cls } = map[status] ?? { label: status, cls: 'bg-slate-100 text-slate-500' }
  return (
    <span className={`inline-block rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  )
}

// ── Single contact row (inside company drawer) ────────────────────────────────

function ContactRow({ contact }: { contact: ProspectContactRead }) {
  const isMatch = contact.title_match
  return (
    <tr className={`border-b border-[var(--oc-border)] transition-colors hover:bg-[var(--oc-surface)] ${isMatch ? 'bg-emerald-50/50' : ''}`}>
      <td className="px-3 py-2.5 text-xs font-medium text-[var(--oc-text)]">
        <span>{contact.first_name} {contact.last_name}</span>
        {isMatch && (
          <span className="ml-1.5 inline-block rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-700">
            Match
          </span>
        )}
      </td>
      <td className="max-w-[180px] truncate px-3 py-2.5 text-xs text-[var(--oc-muted)]" title={contact.title ?? ''}>
        {contact.title ?? <span className="opacity-30">—</span>}
      </td>
      <td className="px-3 py-2.5 text-xs">
        {contact.email ? (
          <a
            href={`mailto:${contact.email}`}
            className="text-[var(--oc-accent-ink)] underline decoration-dotted hover:no-underline"
          >
            {contact.email}
          </a>
        ) : isMatch ? (
          <span className="text-amber-500/70 text-[11px]">not found</span>
        ) : (
          <span className="opacity-20">—</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        {contact.email ? <EmailStatusBadge status={contact.email_status} /> : null}
      </td>
      <td className="px-3 py-2.5 text-xs">
        {contact.linkedin_url ? (
          <a
            href={contact.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--oc-accent-ink)] underline hover:no-underline"
          >
            LinkedIn
          </a>
        ) : (
          <span className="opacity-20">—</span>
        )}
      </td>
    </tr>
  )
}

// ── Title rules manager ───────────────────────────────────────────────────────

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
            <span className="ml-1 font-normal normal-case">— AND within rule, OR between rules</span>
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
            {includeRules.length === 0 && (
              <p className="text-xs text-[var(--oc-muted)]">No include rules yet.</p>
            )}
          </div>
        </div>
        <div>
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">
            Exclude ({excludeRules.length})
            <span className="ml-1 font-normal normal-case">— any keyword disqualifies</span>
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
            {excludeRules.length === 0 && (
              <p className="text-xs text-[var(--oc-muted)]">No exclude rules yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Company contacts drawer ───────────────────────────────────────────────────

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
      .catch(() => setError('Failed to load contacts.'))
      .finally(() => setIsLoading(false))
  }, [company.company_id])

  const displayed = matchedOnly ? contacts.filter((c) => c.title_match) : contacts
  const matchedCount = contacts.filter((c) => c.title_match).length
  const emailCount = contacts.filter((c) => c.email).length

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
          {matchedCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-700">
              {matchedCount} matched
            </span>
          )}
          <span className="text-[11px] text-[var(--oc-muted)]">
            {company.total_count} total · {emailCount} with email
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
        {/* Filter toggle */}
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
            Matched only ({matchedCount})
          </button>
        </div>

        {/* Contacts table */}
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
            <table className="w-full table-fixed text-left">
              <colgroup>
                <col style={{ width: '22%' }} />
                <col style={{ width: '24%' }} />
                <col style={{ width: '28%' }} />
                <col style={{ width: '11%' }} />
                <col style={{ width: '15%' }} />
              </colgroup>
              <thead className="sticky top-0 bg-[var(--oc-surface-strong)]">
                <tr className="border-b border-[var(--oc-border)]">
                  <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Name</th>
                  <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Title</th>
                  <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Email</th>
                  <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Status</th>
                  <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">LinkedIn</th>
                </tr>
              </thead>
              <tbody>
                {displayed.map((c) => (
                  <ContactRow key={c.id} contact={c} />
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Title Match Rules (collapsible at bottom) */}
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

// ── Company row in main list ──────────────────────────────────────────────────

function CompanyRow({ company, onClick }: { company: ContactCompanySummary; onClick: () => void }) {
  const hasMatches = company.title_matched_count > 0
  const hasEmails = company.email_count > 0
  return (
    <tr
      className="cursor-pointer border-b border-[var(--oc-border)] transition-colors hover:bg-[var(--oc-surface)]"
      onClick={onClick}
    >
      <td className="px-3 py-2.5 text-xs font-semibold text-[var(--oc-accent-ink)]">
        {company.domain}
      </td>
      <td className="px-3 py-2.5 text-center text-xs font-bold tabular-nums">
        {hasMatches ? (
          <span className="text-emerald-600">{company.title_matched_count}</span>
        ) : (
          <span className="text-[var(--oc-muted)] opacity-40">0</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-center text-xs tabular-nums text-[var(--oc-text)]">
        {company.total_count}
      </td>
      <td className="px-3 py-2.5 text-center text-xs tabular-nums">
        {hasEmails ? (
          <span className="text-[var(--oc-text)]">{company.email_count}</span>
        ) : (
          <span className="text-[var(--oc-muted)] opacity-40">—</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-right text-[var(--oc-muted)]">
        <span className="text-[10px]">›</span>
      </td>
    </tr>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

export function ContactsView() {
  const [companies, setCompanies] = useState<ContactCompanyListResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [offset, setOffset] = useState(0)
  const [limit] = useState(50)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const [selectedCompany, setSelectedCompany] = useState<ContactCompanySummary | null>(null)

  // Rules (shared, loaded once when drawer first opens)
  const [rules, setRules] = useState<TitleMatchRuleRead[]>([])
  const [isRulesLoading, setIsRulesLoading] = useState(false)
  const [isSeeding, setIsSeeding] = useState(false)
  const [rulesError, setRulesError] = useState('')
  const [deletingRuleIds, setDeletingRuleIds] = useState<Set<string>>(new Set())

  const loadCompanies = useCallback(
    async (off = 0, s = search) => {
      setIsLoading(true)
      setError('')
      try {
        const data = await listContactCompanies({ search: s || undefined, limit, offset: off })
        setCompanies(data)
        setOffset(off)
      } catch {
        setError('Failed to load contacts.')
      } finally {
        setIsLoading(false)
      }
    },
    [search, limit],
  )

  useEffect(() => {
    void loadCompanies(0, search)
  }, [search, loadCompanies])

  const loadRules = useCallback(async () => {
    setIsRulesLoading(true)
    try {
      setRules(await listTitleMatchRules())
      setRulesError('')
    } catch {
      setRulesError('Failed to load rules.')
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
    } catch {
      setRulesError('Failed to create rule.')
    }
  }

  const handleDeleteRule = async (id: string) => {
    if (deletingRuleIds.has(id)) return
    setDeletingRuleIds((prev) => new Set([...prev, id]))
    try {
      await deleteTitleMatchRule(id)
      setRules((r) => r.filter((rule) => rule.id !== id))
    } catch {
      setRulesError('Failed to delete rule.')
    } finally {
      setDeletingRuleIds((prev) => {
        const s = new Set(prev)
        s.delete(id)
        return s
      })
    }
  }

  const handleSeed = async () => {
    setIsSeeding(true)
    try {
      await seedTitleMatchRules()
      await loadRules()
      setRulesError('')
    } catch {
      setRulesError('Failed to seed rules.')
    } finally {
      setIsSeeding(false)
    }
  }

  const totalMatched = companies?.items.reduce((s, c) => s + c.title_matched_count, 0) ?? 0
  const totalEmails = companies?.items.reduce((s, c) => s + c.email_count, 0) ?? 0

  return (
    <div className="flex h-full flex-col gap-4 overflow-hidden p-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-[var(--oc-text)]">Contacts</h2>
          {companies && (
            <p className="text-xs text-[var(--oc-muted)]">
              {companies.total.toLocaleString()} companies · {totalMatched} matched · {totalEmails} with email
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadCompanies(offset)}
            disabled={isLoading}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:opacity-50"
          >
            <IconRefresh size={13} />
            Refresh
          </button>
          <a
            href={getContactsExportUrl()}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] no-underline transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
          >
            <IconDownload size={13} />
            Export all CSV
          </a>
        </div>
      </div>

      {/* Search */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') setSearch(searchInput) }}
          onBlur={() => setSearch(searchInput)}
          placeholder="Search by domain…"
          className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs text-[var(--oc-text)] placeholder:text-[var(--oc-muted)]"
          style={{ minWidth: 220 }}
        />
      </div>

      {/* Table */}
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <div className="flex-1 overflow-auto rounded-2xl border border-[var(--oc-border)]">
        {isLoading && !companies ? (
          <div className="flex h-40 items-center justify-center">
            <p className="text-sm text-[var(--oc-muted)]">Loading…</p>
          </div>
        ) : companies?.items.length === 0 ? (
          <div className="flex h-40 items-center justify-center text-center">
            <div>
              <p className="text-sm font-medium text-[var(--oc-muted)]">No contacts yet</p>
              <p className="mt-1 text-xs text-[var(--oc-muted)]">
                Use "Fetch Contacts" on Possible companies or from an Analysis Run.
              </p>
            </div>
          </div>
        ) : (
          <table className="w-full table-fixed text-left">
            <colgroup>
              <col style={{ width: '42%' }} />
              <col style={{ width: '16%' }} />
              <col style={{ width: '16%' }} />
              <col style={{ width: '16%' }} />
              <col style={{ width: '10%' }} />
            </colgroup>
            <thead className="sticky top-0 bg-[var(--oc-surface-strong)]">
              <tr className="border-b border-[var(--oc-border)]">
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Domain</th>
                <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-widest text-emerald-600">Matched</th>
                <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Total</th>
                <th className="px-3 py-2 text-center text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Emails</th>
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

      {/* Pagination */}
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

      {/* Company drawer */}
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
