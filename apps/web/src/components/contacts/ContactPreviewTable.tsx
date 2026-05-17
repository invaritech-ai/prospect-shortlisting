import type { ContactStage, ProspectContactRead } from '../../lib/types'

function contactStageMeta(stage: ContactStage): { label: string; cls: string } {
  switch (stage) {
    case 'fetched':       return { label: 'Fetched',        cls: 'oc-badge oc-badge-neutral' }
    case 'email_revealed':return { label: 'Email revealed', cls: 'oc-badge oc-badge-warn'    }
    case 'campaign_ready':return { label: 'Campaign Ready', cls: 'oc-badge oc-badge-success' }
    default:              return { label: stage,            cls: 'oc-badge oc-badge-neutral' }
  }
}

function verificationMeta(status: string): { label: string; cls: string } {
  const normalized = (status || 'unknown').toLowerCase()
  switch (normalized) {
    case 'unverified': return { label: 'Unverified', cls: 'oc-badge oc-badge-neutral' }
    case 'valid':      return { label: 'Valid',       cls: 'oc-badge oc-badge-success' }
    case 'invalid':
    case 'not_valid':  return { label: 'Invalid',     cls: 'oc-badge oc-badge-fail'    }
    case 'catch_all':  return { label: 'Catch-all',   cls: 'oc-badge oc-badge-warn'    }
    case 'unknown':    return { label: 'Unknown',     cls: 'oc-badge oc-badge-neutral' }
    default:           return { label: normalized.replace(/_/g, ' '), cls: 'oc-badge oc-badge-neutral' }
  }
}

function providerStatusMeta(status: string | null): { label: string; cls: string } | null {
  if (!status) return null
  switch (status.toLowerCase()) {
    case 'email_revealed': return { label: 'Provider ok',      cls: 'oc-badge oc-badge-info'    }
    case 'unknown':        return { label: 'Provider unknown', cls: 'oc-badge oc-badge-neutral' }
    default:               return { label: status.replace(/_/g, ' '), cls: 'oc-badge oc-badge-neutral' }
  }
}

function sourceProviderMeta(provider: string | null | undefined): { label: string; cls: string } | null {
  const normalized = (provider ?? '').trim().toLowerCase()
  if (!normalized) return null
  if (normalized === 'snov')   return { label: 'SNOV',   cls: 'oc-badge oc-badge-info' }
  if (normalized === 'apollo') return { label: 'APOLLO', cls: 'oc-badge oc-badge-info' }
  return { label: normalized.toUpperCase(), cls: 'oc-badge oc-badge-neutral' }
}

function StatusBadge({ label, cls }: { label: string; cls: string }) {
  return <span className={cls} style={{ fontSize: '0.5625rem', padding: '0.125rem 0.375rem' }}>{label}</span>
}

function ContactRow({ contact }: { contact: ProspectContactRead }) {
  const isMatch = contact.title_match
  const stage = contactStageMeta(contact.pipeline_stage)
  const verification = verificationMeta(contact.verification_status)
  const provider = providerStatusMeta(contact.provider_email_status)
  const sourceProvider = sourceProviderMeta(contact.source_provider)
  const emailList = (contact.emails && contact.emails.length > 0 ? contact.emails : contact.email ? [contact.email] : []) as string[]

  return (
    <tr
      className="border-b border-(--oc-border) transition-colors hover:bg-(--oc-surface)"
      style={isMatch ? { backgroundColor: 'color-mix(in srgb, var(--oc-success-bg) 40%, white)' } : undefined}
    >
      <td className="px-3 py-2.5 text-xs font-medium text-(--oc-text)">
        <span>{contact.first_name} {contact.last_name}</span>
        {isMatch && (
          <span className="oc-badge oc-badge-success" style={{ marginLeft: '0.375rem', fontSize: '0.5625rem', padding: '0.125rem 0.375rem' }}>
            Match
          </span>
        )}
        {sourceProvider && (
          <span className={sourceProvider.cls} style={{ marginLeft: '0.375rem', fontSize: '0.5625rem', padding: '0.125rem 0.375rem' }}>
            {sourceProvider.label}
          </span>
        )}
      </td>
      <td className="max-w-[180px] truncate px-3 py-2.5 text-xs text-(--oc-muted)" title={contact.title ?? ''}>
        {contact.title ?? <span className="opacity-30">—</span>}
      </td>
      <td className="px-3 py-2.5 text-xs">
        {emailList.length > 0 ? (
          <div className="flex flex-col gap-1">
            {emailList.slice(0, 2).map((email) => (
              <a key={email} href={`mailto:${email}`} className="text-(--oc-accent-ink) underline decoration-dotted hover:no-underline">
                {email}
              </a>
            ))}
            {emailList.length > 2 && (
              <span className="text-[10px] text-(--oc-muted)">+{emailList.length - 2} more</span>
            )}
          </div>
        ) : isMatch ? (
          <span style={{ fontSize: '0.6875rem', color: 'var(--oc-warn-text)', opacity: 0.7 }}>not found</span>
        ) : (
          <span className="opacity-20">—</span>
        )}
      </td>
      <td className="px-3 py-2.5"><StatusBadge label={stage.label} cls={stage.cls} /></td>
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge label={verification.label} cls={verification.cls} />
          {provider && <StatusBadge label={provider.label} cls={provider.cls} />}
        </div>
      </td>
      <td className="px-3 py-2.5 text-xs">
        {contact.linkedin_url ? (
          <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-(--oc-accent-ink) underline hover:no-underline">
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
      <thead className="sticky top-0 bg-(--oc-surface-strong)">
        <tr className="border-b border-(--oc-border)">
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">Name</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">Title</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">Email</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">Stage</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">Verification</th>
          <th className="px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-(--oc-muted)">LinkedIn</th>
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
