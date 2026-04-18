import { useEffect, useMemo, useState } from 'react'
import type { CompanyListItem, ContactCompanySummary, MatchGapFilter, ProspectContactRead } from '../../lib/types'
import { getContactsExportUrl, parseUTC } from '../../lib/api'
import { summarizeCompanyContacts } from '../../lib/contactPreview'
import { ContactPreviewTable } from '../contacts/ContactPreviewTable'
import { Drawer } from '../ui/Drawer'
import { IconDownload } from '../ui/icons'

interface CompanyContactsPreviewPanelProps {
  company: CompanyListItem | null
  contacts: ProspectContactRead[]
  summary: ContactCompanySummary | null
  matchGapFilter: MatchGapFilter
  isLoading: boolean
  error: string
  onMatchGapFilterChange: (filter: MatchGapFilter) => void
  onClose: () => void
}

export function CompanyContactsPreviewPanel({
  company,
  contacts,
  summary: summaryFromApi,
  matchGapFilter,
  isLoading,
  error,
  onMatchGapFilterChange,
  onClose,
}: CompanyContactsPreviewPanelProps) {
  const [matchedOnly, setMatchedOnly] = useState(true)

  useEffect(() => {
    if (company) setMatchedOnly(true)
  }, [company?.id])

  const summaryStats = useMemo(() => summarizeCompanyContacts(contacts), [contacts])
  const fetchedCount = isLoading && contacts.length === 0 ? company?.contact_count ?? 0 : summaryStats.total
  const displayedContacts = useMemo(() => {
    const byGap = (() => {
      if (matchGapFilter === 'contacts_no_match') return contacts.filter((contact) => !contact.title_match)
      if (matchGapFilter === 'matched_no_email') return contacts.filter((contact) => contact.title_match && !contact.email)
      if (matchGapFilter === 'ready_candidates') return contacts.filter((contact) => contact.pipeline_stage === 'campaign_ready')
      return contacts
    })()
    if (matchGapFilter !== 'all') return byGap
    return matchedOnly ? byGap.filter((contact) => contact.title_match) : byGap
  }, [contacts, matchGapFilter, matchedOnly])

  if (!company) return null

  const exportUrl = getContactsExportUrl({ companyId: company.id })

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
            {fetchedCount.toLocaleString()} fetched
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-700">
            {(summaryFromApi?.title_matched_count ?? summaryStats.matched).toLocaleString()} matched
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2.5 py-1 text-[11px] font-bold text-violet-700">
            {(summaryFromApi?.unmatched_count ?? Math.max(summaryStats.total - summaryStats.matched, 0)).toLocaleString()} unmatched
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2.5 py-1 text-[11px] font-bold text-orange-700">
            {(summaryFromApi?.matched_no_email_count ?? 0).toLocaleString()} matched/no-email
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-bold text-sky-700">
            {summaryStats.withEmail.toLocaleString()} with email
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-700">
            {summaryStats.verified.toLocaleString()} verified
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-800">
            {summaryStats.campaignReady.toLocaleString()} campaign ready
          </span>
          <span className="text-[11px] text-(--oc-muted)">
            {summaryStats.eligibleToVerify.toLocaleString()} eligible to verify
          </span>
          {summaryFromApi?.last_contact_attempted_at ? (
            <span className="text-[11px] text-(--oc-muted)">
              Last attempted {parseUTC(summaryFromApi.last_contact_attempted_at).toLocaleString()}
            </span>
          ) : null}
        </div>
      }
      headerActions={
        <a
          href={exportUrl}
          className="flex items-center gap-1.5 rounded-lg border border-(--oc-border) bg-white px-3 py-1.5 text-xs font-bold text-(--oc-text) no-underline transition hover:border-(--oc-accent) hover:text-(--oc-accent-ink)"
        >
          <IconDownload size={13} />
          Export CSV
        </a>
      }
    >
      <div className="flex h-full flex-col">
        <div className="flex flex-wrap items-center gap-1.5 border-b border-(--oc-border) px-4 py-2">
          <button
            type="button"
            onClick={() => onMatchGapFilterChange('all')}
            className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition ${
              matchGapFilter === 'all'
                ? 'bg-(--oc-accent) text-white'
                : 'border border-(--oc-border) text-(--oc-muted) hover:text-(--oc-text)'
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => onMatchGapFilterChange('contacts_no_match')}
            className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition ${
              matchGapFilter === 'contacts_no_match'
                ? 'bg-(--oc-accent) text-white'
                : 'border border-(--oc-border) text-(--oc-muted) hover:text-(--oc-text)'
            }`}
          >
            Contacts no match
          </button>
          <button
            type="button"
            onClick={() => onMatchGapFilterChange('matched_no_email')}
            className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition ${
              matchGapFilter === 'matched_no_email'
                ? 'bg-(--oc-accent) text-white'
                : 'border border-(--oc-border) text-(--oc-muted) hover:text-(--oc-text)'
            }`}
          >
            Matched no email
          </button>
          <button
            type="button"
            onClick={() => onMatchGapFilterChange('ready_candidates')}
            className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition ${
              matchGapFilter === 'ready_candidates'
                ? 'bg-(--oc-accent) text-white'
                : 'border border-(--oc-border) text-(--oc-muted) hover:text-(--oc-text)'
            }`}
          >
            Ready candidates
          </button>
        </div>
        <div className="flex items-center gap-2 border-b border-(--oc-border) px-4 py-2.5">
          <button
            type="button"
            onClick={() => setMatchedOnly(true)}
            disabled={matchGapFilter !== 'all'}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              matchedOnly
                ? 'bg-emerald-600 text-white'
                : 'border border-(--oc-border) bg-white text-(--oc-muted) hover:text-(--oc-text)'
            } ${matchGapFilter !== 'all' ? 'opacity-50' : ''}`}
          >
            Matched only ({summaryStats.matched})
          </button>
          <button
            type="button"
            onClick={() => setMatchedOnly(false)}
            disabled={matchGapFilter !== 'all'}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              !matchedOnly
                ? 'bg-(--oc-accent) text-white'
                : 'border border-(--oc-border) bg-white text-(--oc-muted) hover:text-(--oc-text)'
            } ${matchGapFilter !== 'all' ? 'opacity-50' : ''}`}
          >
            All ({fetchedCount})
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {error ? <p className="px-4 py-3 text-xs text-rose-600">{error}</p> : null}
          {isLoading ? (
            <div className="flex h-32 items-center justify-center">
              <p className="text-sm text-(--oc-muted)">Loading contacts…</p>
            </div>
          ) : displayedContacts.length === 0 ? (
            <div className="flex h-32 items-center justify-center px-4 text-center">
              {matchedOnly && summaryStats.total > 0 ? (
                <div>
                  <p className="text-sm font-medium text-(--oc-muted)">No title-matched contacts</p>
                  <button
                    type="button"
                    onClick={() => setMatchedOnly(false)}
                    className="mt-1 text-xs text-(--oc-accent-ink) underline hover:no-underline"
                  >
                    Show all {summaryStats.total} contacts
                  </button>
                </div>
              ) : (
                <p className="text-sm text-(--oc-muted)">No contacts fetched for this company yet.</p>
              )}
            </div>
          ) : (
            <ContactPreviewTable contacts={displayedContacts} />
          )}
        </div>
      </div>
    </Drawer>
  )
}
