import type { MockContactRow } from '../../../lib/useAppData'
import { Drawer } from '../../ui/Drawer'

interface ContactDrawerProps {
  row: MockContactRow | null
  onClose: () => void
}

function initials(name: string) {
  return name.split(' ').map((n) => n[0]).slice(0, 2).join('').toUpperCase()
}

export function ContactDrawer({ row, onClose }: ContactDrawerProps) {
  if (!row) return null

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title={row.domain}
      subtitle={`S3 · ${row.contactsFound} contacts · ${row.emailsFound} emails`}
      accentColor="var(--s3)"
    >
      {row.contacts.length === 0 ? (
        <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--oc-muted)', fontSize: '0.9375rem' }}>
          No contacts found for this company.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {row.contacts.map((contact) => (
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
              {/* Avatar */}
              <div style={{
                flexShrink: 0,
                width: '38px', height: '38px', borderRadius: '0.5rem',
                background: 'color-mix(in srgb, var(--s3) 15%, var(--oc-bg))',
                border: '1.5px solid color-mix(in srgb, var(--s3) 25%, var(--oc-border))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 800,
                color: 'var(--s3-text)',
              }}>
                {initials(contact.name)}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Name + title row */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--oc-text)', lineHeight: 1.2 }}>
                      {contact.name}
                    </div>
                    <div style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>
                      {contact.title}
                    </div>
                  </div>
                  {contact.linkedinUrl && (
                    <a
                      href={contact.linkedinUrl}
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
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6zM2 9h4v12H2z"/>
                        <circle cx="4" cy="4" r="2"/>
                      </svg>
                    </a>
                  )}
                </div>

                {/* Email */}
                <div style={{ marginTop: '0.5rem' }}>
                  {contact.email ? (
                    <a
                      href={`mailto:${contact.email}`}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
                        fontFamily: 'var(--font-mono)', fontSize: '0.8125rem',
                        color: 'var(--s3)', textDecoration: 'none', fontWeight: 500,
                      }}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                        <polyline points="22,6 12,13 2,6"/>
                      </svg>
                      {contact.email}
                    </a>
                  ) : (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', fontSize: '0.8125rem', color: 'var(--oc-muted)', fontStyle: 'italic' }}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                        <polyline points="22,6 12,13 2,6"/>
                      </svg>
                      No email found
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Drawer>
  )
}
