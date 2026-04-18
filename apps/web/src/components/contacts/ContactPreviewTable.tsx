import type { ContactStage, ProspectContactRead } from '../../lib/types'

function contactStageMeta(stage: ContactStage): { label: string; cls: string } {
  switch (stage) {
    case 'fetched':
      return { label: 'Fetched', cls: 'bg-slate-100 text-slate-700' }
    case 'verified':
      return { label: 'Verified', cls: 'bg-amber-100 text-amber-700' }
    case 'campaign_ready':
      return { label: 'Campaign Ready', cls: 'bg-emerald-100 text-emerald-700' }
    default:
      return { label: stage, cls: 'bg-slate-100 text-slate-700' }
  }
}

function verificationMeta(status: string): { label: string; cls: string } {
  const normalized = (status || 'unknown').toLowerCase()
  switch (normalized) {
    case 'unverified':
      return { label: 'Unverified', cls: 'bg-slate-100 text-slate-700' }
    case 'valid':
      return { label: 'Valid', cls: 'bg-emerald-100 text-emerald-700' }
    case 'invalid':
    case 'not_valid':
      return { label: 'Invalid', cls: 'bg-rose-100 text-rose-700' }
    case 'catch_all':
      return { label: 'Catch-all', cls: 'bg-amber-100 text-amber-700' }
    case 'unknown':
      return { label: 'Unknown', cls: 'bg-slate-100 text-slate-500' }
    default:
      return { label: normalized.replace(/_/g, ' '), cls: 'bg-slate-100 text-slate-700' }
  }
}

function providerStatusMeta(status: string | null): { label: string; cls: string } | null {
  if (!status) return null
  switch (status.toLowerCase()) {
    case 'verified':
      return { label: 'Provider ok', cls: 'bg-sky-100 text-sky-700' }
    case 'unknown':
      return { label: 'Provider unknown', cls: 'bg-slate-100 text-slate-500' }
    default:
      return { label: status.replace(/_/g, ' '), cls: 'bg-slate-100 text-slate-700' }
  }
}

function StatusBadge({ label, cls }: { label: string; cls: string }) {
  return (
    <span className={`inline-flex rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  )
}

function ContactRow({ contact }: { contact: ProspectContactRead }) {
  const isMatch = contact.title_match
  const stage = contactStageMeta(contact.pipeline_stage)
  const verification = verificationMeta(contact.verification_status)
  const provider = providerStatusMeta(contact.provider_email_status)

  return (
    <tr className={`border-b border-[var(--oc-border)] transition-colors hover:bg-[var(--oc-surface)] ${isMatch ? 'bg-emerald-50/40' : ''}`}>
      <td className="px-3 py-2.5 text-xs font-medium text-[var(--oc-text)]">
        <span>{contact.first_name} {contact.last_name}</span>
        {isMatch ? (
          <span className="ml-1.5 inline-block rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-700">
            Match
          </span>
        ) : null}
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
          <span className="text-[11px] text-amber-500/70">not found</span>
        ) : (
          <span className="opacity-20">—</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <StatusBadge label={stage.label} cls={stage.cls} />
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge label={verification.label} cls={verification.cls} />
          {provider ? <StatusBadge label={provider.label} cls={provider.cls} /> : null}
        </div>
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

interface ContactPreviewTableProps {
  contacts: ProspectContactRead[]
}

export function ContactPreviewTable({ contacts }: ContactPreviewTableProps) {
  return (
    <table className="w-full table-fixed text-left">
      <colgroup>
        <col style={{ width: '18%' }} />
        <col style={{ width: '22%' }} />
        <col style={{ width: '24%' }} />
        <col style={{ width: '12%' }} />
        <col style={{ width: '16%' }} />
        <col style={{ width: '8%' }} />
      </colgroup>
      <thead className="sticky top-0 bg-[var(--oc-surface-strong)]">
        <tr className="border-b border-[var(--oc-border)]">
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Name</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Title</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Email</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Stage</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">Verification</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">LinkedIn</th>
        </tr>
      </thead>
      <tbody>
        {contacts.map((contact) => (
          <ContactRow key={contact.id} contact={contact} />
        ))}
      </tbody>
    </table>
  )
}
