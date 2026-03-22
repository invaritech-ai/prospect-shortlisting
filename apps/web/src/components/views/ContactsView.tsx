import { useCallback, useEffect, useState } from 'react'
import type { ContactListResponse, ProspectContactRead, TitleMatchRuleRead } from '../../lib/types'
import {
  createTitleMatchRule,
  deleteTitleMatchRule,
  getContactsExportUrl,
  listContacts,
  listTitleMatchRules,
  seedTitleMatchRules,
} from '../../lib/api'
import { IconDownload, IconRefresh, IconTrash, IconPlus } from '../ui/icons'

const EMAIL_STATUS_LABELS: Record<string, string> = {
  unverified: 'Unverified',
  valid: 'Valid',
  unknown: 'Unknown',
  not_valid: 'Invalid',
}

function EmailStatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    valid: 'oc-badge-success',
    not_valid: 'oc-badge-fail',
    unverified: 'oc-badge-info',
    unknown: '',
  }
  return (
    <span className={`oc-badge ${colorMap[status] ?? ''}`}>
      {EMAIL_STATUS_LABELS[status] ?? status}
    </span>
  )
}

function ContactRow({ contact }: { contact: ProspectContactRead }) {
  return (
    <tr className="border-b border-[var(--oc-border)] hover:bg-[var(--oc-surface)] transition-colors">
      <td className="px-3 py-2 text-xs font-medium text-[var(--oc-text)]">
        {contact.first_name} {contact.last_name}
      </td>
      <td className="px-3 py-2 text-xs text-[var(--oc-muted)] max-w-[200px] truncate" title={contact.title ?? ''}>
        {contact.title ?? <span className="opacity-40">—</span>}
      </td>
      <td className="px-3 py-2 text-xs">
        {contact.title_match ? (
          <span className="oc-badge oc-badge-success">Matched</span>
        ) : (
          <span className="oc-badge">No</span>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-[var(--oc-muted)]">
        {contact.email ?? <span className="opacity-40">—</span>}
      </td>
      <td className="px-3 py-2">
        <EmailStatusBadge status={contact.email_status} />
      </td>
      <td className="px-3 py-2 text-xs">
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
          <span className="opacity-40">—</span>
        )}
      </td>
      <td className="px-3 py-2 text-[10px] text-[var(--oc-muted)]">
        {contact.snov_confidence != null ? `${Math.round(contact.snov_confidence * 100)}%` : '—'}
      </td>
    </tr>
  )
}

interface TitleRulesManagerProps {
  rules: TitleMatchRuleRead[]
  onAdd: (rule_type: 'include' | 'exclude', keywords: string) => void
  onDelete: (id: string) => void
  deletingIds: Set<string>
  onSeed: () => void
  isSeeding: boolean
}

function TitleRulesManager({ rules, onAdd, onDelete, deletingIds, onSeed, isSeeding }: TitleRulesManagerProps) {
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
          <span className="ml-2 font-normal text-[var(--oc-muted)]">({rules.length} rules)</span>
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

      {/* Add rule */}
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
              <div key={r.id} className="flex items-center justify-between rounded-lg border border-[var(--oc-border)] bg-[var(--oc-surface)] px-2.5 py-1.5">
                <span className="text-xs text-[var(--oc-text)]">{r.keywords}</span>
                <button
                  type="button"
                  onClick={() => onDelete(r.id)}
                  disabled={deletingIds.has(r.id)}
                  className="ml-2 text-[var(--oc-muted)] transition hover:text-rose-600 disabled:opacity-40 disabled:cursor-not-allowed"
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
              <div key={r.id} className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5">
                <span className="text-xs text-rose-700">{r.keywords}</span>
                <button
                  type="button"
                  onClick={() => onDelete(r.id)}
                  disabled={deletingIds.has(r.id)}
                  className="ml-2 text-rose-400 transition hover:text-rose-700 disabled:opacity-40 disabled:cursor-not-allowed"
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

export function ContactsView() {
  const [contacts, setContacts] = useState<ContactListResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [offset, setOffset] = useState(0)
  const [limit] = useState(100)
  const [titleMatchFilter, setTitleMatchFilter] = useState<boolean | undefined>(undefined)
  const [emailStatusFilter, setEmailStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')

  const [rules, setRules] = useState<TitleMatchRuleRead[]>([])
  const [isRulesOpen, setIsRulesOpen] = useState(false)
  const [isRulesLoading, setIsRulesLoading] = useState(false)
  const [isSeeding, setIsSeeding] = useState(false)
  const [rulesError, setRulesError] = useState('')
  const [deletingRuleIds, setDeletingRuleIds] = useState<Set<string>>(new Set())

  const loadContacts = useCallback(async (off = 0, tm = titleMatchFilter, es = emailStatusFilter, s = search) => {
    setIsLoading(true)
    setError('')
    try {
      const data = await listContacts({ titleMatch: tm, emailStatus: es || undefined, search: s || undefined, limit, offset: off })
      setContacts(data)
      setOffset(off)
    } catch {
      setError('Failed to load contacts.')
    } finally {
      setIsLoading(false)
    }
  }, [titleMatchFilter, emailStatusFilter, search, limit])

  const loadRules = useCallback(async () => {
    setIsRulesLoading(true)
    try {
      const data = await listTitleMatchRules()
      setRules(data)
      setRulesError('')
    } catch {
      setRulesError('Failed to load rules.')
    } finally {
      setIsRulesLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadContacts(0, titleMatchFilter, emailStatusFilter, search)
  }, [titleMatchFilter, emailStatusFilter, search, loadContacts])

  useEffect(() => {
    if (isRulesOpen && rules.length === 0) void loadRules()
  }, [isRulesOpen, rules.length, loadRules])

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
      setDeletingRuleIds((prev) => { const s = new Set(prev); s.delete(id); return s })
    }
  }

  const handleSeed = async () => {
    setIsSeeding(true)
    try {
      await seedTitleMatchRules()
      await loadRules()
    } catch {
      setRulesError('Failed to seed rules.')
    } finally {
      setIsSeeding(false)
    }
  }

  const totalMatched = contacts?.items.filter((c) => c.title_match).length ?? 0
  const totalWithEmail = contacts?.items.filter((c) => c.email).length ?? 0

  return (
    <div className="flex h-full flex-col gap-4 overflow-hidden p-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-[var(--oc-text)]">Contacts</h2>
          {contacts && (
            <p className="text-xs text-[var(--oc-muted)]">
              {contacts.total.toLocaleString()} total · {totalMatched} title-matched · {totalWithEmail} with email
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void loadContacts(offset)}
            disabled={isLoading}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:opacity-50"
          >
            <IconRefresh size={13} />
            Refresh
          </button>
          <a
            href={getContactsExportUrl(titleMatchFilter, emailStatusFilter || undefined)}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] no-underline transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
          >
            <IconDownload size={13} />
            Export CSV
          </a>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') setSearch(searchInput) }}
          onBlur={() => setSearch(searchInput)}
          placeholder="Search name, email, title…"
          className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs text-[var(--oc-text)] placeholder:text-[var(--oc-muted)]"
          style={{ minWidth: 200 }}
        />
        <select
          value={titleMatchFilter === undefined ? '' : String(titleMatchFilter)}
          onChange={(e) => setTitleMatchFilter(e.target.value === '' ? undefined : e.target.value === 'true')}
          className="rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1.5 text-xs text-[var(--oc-text)]"
        >
          <option value="">All titles</option>
          <option value="true">Title matched</option>
          <option value="false">Not matched</option>
        </select>
        <select
          value={emailStatusFilter}
          onChange={(e) => setEmailStatusFilter(e.target.value)}
          className="rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1.5 text-xs text-[var(--oc-text)]"
        >
          <option value="">All email statuses</option>
          <option value="valid">Valid</option>
          <option value="unverified">Unverified</option>
          <option value="unknown">Unknown</option>
          <option value="not_valid">Invalid</option>
        </select>
      </div>

      {/* Title rules collapsible */}
      <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface-strong)]">
        <button
          type="button"
          onClick={() => setIsRulesOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left"
        >
          <span className="text-xs font-bold text-[var(--oc-text)]">
            Title Match Rules
            {rules.length > 0 && <span className="ml-2 font-normal text-[var(--oc-muted)]">({rules.length})</span>}
          </span>
          <span className="text-[10px] text-[var(--oc-muted)]">{isRulesOpen ? 'Collapse ▲' : 'Expand ▼'}</span>
        </button>
        {isRulesOpen && (
          <div className="border-t border-[var(--oc-border)] p-4">
            {isRulesLoading ? (
              <p className="text-xs text-[var(--oc-muted)]">Loading rules…</p>
            ) : (
              <>
                {rulesError && <p className="mb-2 text-xs text-rose-600">{rulesError}</p>}
                <TitleRulesManager
                  rules={rules}
                  onAdd={(rt, kw) => void handleAddRule(rt, kw)}
                  onDelete={(id) => void handleDeleteRule(id)}
                  deletingIds={deletingRuleIds}
                  onSeed={() => void handleSeed()}
                  isSeeding={isSeeding}
                />
              </>
            )}
          </div>
        )}
      </div>

      {/* Table */}
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <div className="flex-1 overflow-auto rounded-2xl border border-[var(--oc-border)]">
        {isLoading && !contacts ? (
          <div className="flex h-40 items-center justify-center">
            <p className="text-sm text-[var(--oc-muted)]">Loading contacts…</p>
          </div>
        ) : contacts?.items.length === 0 ? (
          <div className="flex h-40 items-center justify-center">
            <div className="text-center">
              <p className="text-sm font-medium text-[var(--oc-muted)]">No contacts yet</p>
              <p className="mt-1 text-xs text-[var(--oc-muted)]">
                Use "Fetch Contacts" on Possible companies or from an Analysis Run.
              </p>
            </div>
          </div>
        ) : (
          <table className="w-full table-fixed text-left">
            <colgroup>
              <col style={{ width: '18%' }} />
              <col style={{ width: '22%' }} />
              <col style={{ width: '8%' }} />
              <col style={{ width: '22%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '10%' }} />
            </colgroup>
            <thead className="sticky top-0 bg-[var(--oc-surface-strong)]">
              <tr className="border-b border-[var(--oc-border)]">
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Name</th>
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Title</th>
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Match</th>
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Email</th>
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Status</th>
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">LinkedIn</th>
                <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {contacts?.items.map((c) => (
                <ContactRow key={c.id} contact={c} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {contacts && (contacts.has_more || offset > 0) && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-[var(--oc-muted)]">
            {offset + 1}–{Math.min(offset + limit, contacts.total)} of {contacts.total.toLocaleString()}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void loadContacts(Math.max(offset - limit, 0))}
              disabled={offset === 0 || isLoading}
              className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => void loadContacts(offset + limit)}
              disabled={!contacts.has_more || isLoading}
              className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
