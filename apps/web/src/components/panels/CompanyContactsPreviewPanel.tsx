import { useEffect, useMemo, useState } from 'react'
import type { CompanyListItem, ProspectContactRead } from '../../lib/types'
import { getContactsExportUrl } from '../../lib/api'
import { summarizeCompanyContacts } from '../../lib/contactPreview'
import { ContactPreviewTable } from '../contacts/ContactPreviewTable'
import { Drawer } from '../ui/Drawer'
import { IconDownload } from '../ui/icons'

interface CompanyContactsPreviewPanelProps {
  company: CompanyListItem | null
  contacts: ProspectContactRead[]
  isLoading: boolean
  error: string
  onClose: () => void
}

export function CompanyContactsPreviewPanel({
  company,
  contacts,
  isLoading,
  error,
  onClose,
}: CompanyContactsPreviewPanelProps) {
  const [matchedOnly, setMatchedOnly] = useState(true)

  useEffect(() => {
    if (company) setMatchedOnly(true)
  }, [company?.id])

  const summary = useMemo(() => summarizeCompanyContacts(contacts), [contacts])
  const fetchedCount = isLoading && contacts.length === 0 ? company?.contact_count ?? 0 : summary.total
  const displayedContacts = matchedOnly ? contacts.filter((contact) => contact.title_match) : contacts

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
            {summary.matched.toLocaleString()} matched
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-bold text-sky-700">
            {summary.withEmail.toLocaleString()} with email
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-700">
            {summary.verified.toLocaleString()} verified
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-800">
            {summary.campaignReady.toLocaleString()} campaign ready
          </span>
          <span className="text-[11px] text-[var(--oc-muted)]">
            {summary.eligibleToVerify.toLocaleString()} eligible to verify
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
            onClick={() => setMatchedOnly(true)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              matchedOnly
                ? 'bg-emerald-600 text-white'
                : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
            }`}
          >
            Matched only ({summary.matched})
          </button>
          <button
            type="button"
            onClick={() => setMatchedOnly(false)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
              !matchedOnly
                ? 'bg-[var(--oc-accent)] text-white'
                : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
            }`}
          >
            All ({fetchedCount})
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {error ? <p className="px-4 py-3 text-xs text-rose-600">{error}</p> : null}
          {isLoading ? (
            <div className="flex h-32 items-center justify-center">
              <p className="text-sm text-[var(--oc-muted)]">Loading contacts…</p>
            </div>
          ) : displayedContacts.length === 0 ? (
            <div className="flex h-32 items-center justify-center px-4 text-center">
              {matchedOnly && summary.total > 0 ? (
                <div>
                  <p className="text-sm font-medium text-[var(--oc-muted)]">No title-matched contacts</p>
                  <button
                    type="button"
                    onClick={() => setMatchedOnly(false)}
                    className="mt-1 text-xs text-[var(--oc-accent-ink)] underline hover:no-underline"
                  >
                    Show all {summary.total} contacts
                  </button>
                </div>
              ) : (
                <p className="text-sm text-[var(--oc-muted)]">No contacts fetched for this company yet.</p>
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
