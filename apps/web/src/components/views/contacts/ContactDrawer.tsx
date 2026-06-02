import { useEffect, useState } from 'react'
import { listContacts, listFetchedPeople } from '../../../lib/api'
import type { ContactRead, EmailFetchCompanyRow, FetchedPersonRead } from '../../../lib/types'
import { parseApiError } from '../../../lib/utils'
import { Drawer } from '../../ui/Drawer'
import { ExternalLink, Loader2, Mail } from 'lucide-react'

const NO_EMAIL_PAGE_SIZE = 100
const FETCHED_PEOPLE_PAGE_SIZE = 100

interface ContactDrawerProps {
  campaignId: string
  row: EmailFetchCompanyRow | null
  onClose: () => void
}

function initials(name: string) {
  return name.split(' ').map((n) => n[0]).slice(0, 2).join('').toUpperCase()
}

function contactName(contact: ContactRead): string {
  return `${contact.first_name} ${contact.last_name}`.trim() || 'Unknown contact'
}

export function ContactDrawer({ campaignId, row, onClose }: ContactDrawerProps) {
  const [emailContacts, setEmailContacts] = useState<ContactRead[]>([])
  const [noEmailContacts, setNoEmailContacts] = useState<ContactRead[]>([])
  const [unusedFetchedPeople, setUnusedFetchedPeople] = useState<FetchedPersonRead[]>([])
  const [noEmailTotal, setNoEmailTotal] = useState(0)
  const [unusedFetchedTotal, setUnusedFetchedTotal] = useState(0)
  const [noEmailOffset, setNoEmailOffset] = useState(0)
  const [unusedFetchedOffset, setUnusedFetchedOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadingMoreFetched, setLoadingMoreFetched] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!row) return
    let cancelled = false
    void Promise.resolve()
      .then(() => {
        if (cancelled) return null
        setLoading(true)
        setError('')
        setEmailContacts([])
        setNoEmailContacts([])
        setUnusedFetchedPeople([])
        setNoEmailTotal(0)
        setUnusedFetchedTotal(0)
        setNoEmailOffset(0)
        setUnusedFetchedOffset(0)
        return Promise.all([
          listContacts(campaignId, { domainId: row.domain_id, hasEmail: true, limit: 200 }),
          listContacts(campaignId, { domainId: row.domain_id, hasEmail: false, limit: NO_EMAIL_PAGE_SIZE, offset: 0 }),
          listFetchedPeople(campaignId, { domainId: row.domain_id, status: 'unused', limit: FETCHED_PEOPLE_PAGE_SIZE, offset: 0 }),
        ])
      })
      .then((res) => {
        if (cancelled || !res) return
        const [emailRes, noEmailRes, unusedFetchedRes] = res
        setEmailContacts(emailRes.items)
        setNoEmailContacts(noEmailRes.items)
        setUnusedFetchedPeople(unusedFetchedRes.items)
        setNoEmailTotal(noEmailRes.total)
        setUnusedFetchedTotal(unusedFetchedRes.total)
        setNoEmailOffset(noEmailRes.items.length)
        setUnusedFetchedOffset(unusedFetchedRes.items.length)
      })
      .catch((err) => {
        if (cancelled) return
        setError(parseApiError(err))
        setEmailContacts([])
        setNoEmailContacts([])
        setUnusedFetchedPeople([])
        setNoEmailTotal(0)
        setUnusedFetchedTotal(0)
        setNoEmailOffset(0)
        setUnusedFetchedOffset(0)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [campaignId, row])

  if (!row) return null
  const totalLoaded = emailContacts.length + noEmailContacts.length + unusedFetchedPeople.length
  const hasMoreNoEmail = noEmailOffset < noEmailTotal
  const hasMoreUnusedFetched = unusedFetchedOffset < unusedFetchedTotal

  const loadMoreNoEmailContacts = () => {
    if (!row || loadingMore || !hasMoreNoEmail) return
    setLoadingMore(true)
    setError('')
    void listContacts(campaignId, {
      domainId: row.domain_id,
      hasEmail: false,
      limit: NO_EMAIL_PAGE_SIZE,
      offset: noEmailOffset,
    })
      .then((res) => {
        setNoEmailContacts((current) => [...current, ...res.items])
        setNoEmailTotal(res.total)
        setNoEmailOffset((current) => current + res.items.length)
      })
      .catch((err) => setError(parseApiError(err)))
      .finally(() => setLoadingMore(false))
  }

  const loadMoreFetchedPeople = () => {
    if (!row || loadingMoreFetched || !hasMoreUnusedFetched) return
    setLoadingMoreFetched(true)
    setError('')
    void listFetchedPeople(campaignId, {
      domainId: row.domain_id,
      status: 'unused',
      limit: FETCHED_PEOPLE_PAGE_SIZE,
      offset: unusedFetchedOffset,
    })
      .then((res) => {
        setUnusedFetchedPeople((current) => [...current, ...res.items])
        setUnusedFetchedTotal(res.total)
        setUnusedFetchedOffset((current) => current + res.items.length)
      })
      .catch((err) => setError(parseApiError(err)))
      .finally(() => setLoadingMoreFetched(false))
  }

  const renderContact = (contact: ContactRead) => {
    const name = contactName(contact)
    return (
      <div
        key={contact.id}
        style={{
          padding: '0.875rem 1rem',
          borderRadius: '0.875rem',
          border: '1.5px solid var(--oc-border)',
          background: 'var(--oc-surface)',
          display: 'flex', gap: '0.875rem', alignItems: 'flex-start',
        }}
      >
        <div style={{
          flexShrink: 0,
          width: '38px', height: '38px', borderRadius: '0.5rem',
          background: 'color-mix(in srgb, var(--s3) 15%, var(--oc-bg))',
          border: '1.5px solid color-mix(in srgb, var(--s3) 25%, var(--oc-border))',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 800,
          color: 'var(--s3-text)',
        }}>
          {initials(name)}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--oc-text)', lineHeight: 1.2 }}>
                {name}
              </div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>
                {contact.title}
              </div>
            </div>
            {contact.linkedin_url && (
              <a
                href={contact.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                title="LinkedIn profile"
                style={{
                  flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '30px', height: '30px', borderRadius: '0.375rem',
                  border: '1.5px solid var(--oc-border)', color: 'var(--oc-muted)',
                  textDecoration: 'none', transition: 'all 140ms',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#0a66c2'; e.currentTarget.style.color = '#0a66c2' }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)'; e.currentTarget.style.color = 'var(--oc-muted)' }}
              >
                <ExternalLink size={14} />
              </a>
            )}
          </div>

          <div style={{ marginTop: '0.5rem' }}>
            {contact.selected_email ? (
              <a
                href={`mailto:${contact.selected_email}`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
                  fontFamily: 'var(--font-mono)', fontSize: '0.8125rem',
                  color: 'var(--s3)', textDecoration: 'none', fontWeight: 500,
                }}
              >
                <Mail size={12} strokeWidth={2.5} />
                {contact.selected_email}
              </a>
            ) : (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8125rem', color: 'var(--oc-muted)', fontStyle: 'italic' }}>
                <Mail size={12} strokeWidth={2} />
                No email found
              </span>
            )}
          </div>
          {contact.verification_status && (
            <div style={{ marginTop: '0.375rem', fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
              Verification: {contact.verification_status}
            </div>
          )}
        </div>
      </div>
    )
  }

  const renderFetchedPerson = (person: FetchedPersonRead) => {
    const name = `${person.first_name} ${person.last_name}`.trim() || 'Unknown person'
    return (
      <div
        key={person.id}
        style={{
          padding: '0.875rem 1rem',
          borderRadius: '0.875rem',
          border: '1.5px solid var(--oc-border)',
          background: 'color-mix(in srgb, var(--oc-bg) 65%, var(--oc-surface))',
          display: 'flex', gap: '0.875rem', alignItems: 'flex-start',
        }}
      >
        <div style={{
          flexShrink: 0,
          width: '38px', height: '38px', borderRadius: '0.5rem',
          background: 'var(--oc-surface)',
          border: '1.5px solid var(--oc-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 800,
          color: 'var(--oc-muted)',
        }}>
          {initials(name)}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--oc-text)', lineHeight: 1.2 }}>
                {name}
              </div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>
                {person.title || 'Unknown title'}
              </div>
            </div>
            {person.linkedin_url && (
              <a
                href={person.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                title="Source profile"
                style={{
                  flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '30px', height: '30px', borderRadius: '0.375rem',
                  border: '1.5px solid var(--oc-border)', color: 'var(--oc-muted)',
                  textDecoration: 'none',
                }}
              >
                <ExternalLink size={14} />
              </a>
            )}
          </div>
          <div style={{ marginTop: '0.5rem', display: 'flex', flexWrap: 'wrap', gap: '0.375rem', alignItems: 'center' }}>
            <span style={{
              fontSize: '0.6875rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: 0,
              color: 'var(--oc-muted)',
              border: '1px solid var(--oc-border)',
              borderRadius: '999px',
              padding: '0.125rem 0.375rem',
            }}>
              {person.provider}
            </span>
            <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
              {person.match_reason || person.match_status.replace(/_/g, ' ')}
            </span>
          </div>
          {person.email_lookup_attempted && (
            <div style={{ marginTop: '0.375rem', fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
              {person.email_result ? person.email_result : 'No email found'}
            </div>
          )}
        </div>
      </div>
    )
  }

  const sectionTitle = (label: string, count: number) => (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '0.75rem',
      marginTop: '0.25rem',
      fontSize: '0.75rem',
      fontWeight: 800,
      color: 'var(--oc-muted)',
      textTransform: 'uppercase',
      letterSpacing: 0,
    }}>
      <span>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)' }}>{count}</span>
    </div>
  )

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title={row.domain}
      subtitle={`S3 · ${row.contacts_found} contacts · ${row.emails_found} emails · ${row.fetched_people_found} fetched`}
      accentColor="var(--s3)"
    >
      {loading ? (
        <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--oc-muted)', fontSize: '0.9375rem', display: 'flex', justifyContent: 'center', gap: '0.5rem', alignItems: 'center' }}>
          <Loader2 size={15} style={{ animation: 'spin 0.7s linear infinite' }} />
          Loading contacts
        </div>
      ) : error ? (
        <div style={{ padding: '2rem 1rem', color: 'var(--oc-fail-text)', fontSize: '0.875rem' }}>
          {error}
        </div>
      ) : totalLoaded === 0 ? (
        <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
          No contacts found for this company.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {sectionTitle('Qualified contacts', emailContacts.length + noEmailContacts.length)}
          {emailContacts.map(renderContact)}
          {noEmailContacts.map(renderContact)}
          {hasMoreNoEmail && (
            <button
              type="button"
              onClick={loadMoreNoEmailContacts}
              disabled={loadingMore}
              style={{
                alignSelf: 'center',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                minHeight: '38px', padding: '0.5rem 0.875rem', borderRadius: '0.5rem',
                border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                color: 'var(--oc-text)', fontSize: '0.8125rem', fontWeight: 700,
                cursor: loadingMore ? 'not-allowed' : 'pointer', opacity: loadingMore ? 0.7 : 1,
              }}
            >
              {loadingMore && <Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite' }} />}
              Load more
            </button>
          )}
          {unusedFetchedPeople.length > 0 && (
            <>
              {sectionTitle('Fetched people not used', unusedFetchedTotal)}
              {unusedFetchedPeople.map(renderFetchedPerson)}
              {hasMoreUnusedFetched && (
                <button
                  type="button"
                  onClick={loadMoreFetchedPeople}
                  disabled={loadingMoreFetched}
                  style={{
                    alignSelf: 'center',
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
                    minHeight: '38px', padding: '0.5rem 0.875rem', borderRadius: '0.5rem',
                    border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                    color: 'var(--oc-text)', fontSize: '0.8125rem', fontWeight: 700,
                    cursor: loadingMoreFetched ? 'not-allowed' : 'pointer', opacity: loadingMoreFetched ? 0.7 : 1,
                  }}
                >
                  {loadingMoreFetched && <Loader2 size={14} style={{ animation: 'spin 0.7s linear infinite' }} />}
                  Load more fetched people
                </button>
              )}
            </>
          )}
        </div>
      )}
    </Drawer>
  )
}
