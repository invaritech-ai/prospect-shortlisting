import { useState, useRef } from 'react'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'

const DEFAULT_TITLES = `# Target job titles (exact or partial match)

## C-Suite
CEO, Chief Executive Officer
CTO, Chief Technology Officer
COO, Chief Operating Officer
CFO, Chief Financial Officer
CPO, Chief Product Officer

## VP-level
VP Engineering
VP Product
VP Sales
VP Marketing
Head of Engineering
Head of Product

## Director-level
Director of Engineering
Director of Product
Engineering Manager`

const PROVIDERS = [
  { id: 'apollo',  label: 'Apollo.io',  desc: 'Best for US/global SMB & mid-market' },
  { id: 'snov',    label: 'Snov.io',    desc: 'Good for European companies' },
]

function Spinner() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
      style={{ animation: 'spin 0.7s linear infinite', flexShrink: 0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  )
}

interface ContactsSettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
}

export function ContactsSettingsDrawer({ isOpen, onClose }: ContactsSettingsDrawerProps) {
  const [titles, setTitles]     = useState(DEFAULT_TITLES)
  const [provider, setProvider] = useState('apollo')
  const [activeTab, setActiveTab] = useState<'titles' | 'provider'>('titles')

  const [isDirty, setIsDirty]         = useState(false)
  const [isSaving, setIsSaving]       = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [showUnsaved, setShowUnsaved] = useState(false)
  const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function markDirty() { setIsDirty(true); setSaveSuccess(false) }

  function handleClose() {
    if (isDirty) { setShowUnsaved(true) } else { onClose() }
  }

  async function handleSave() {
    setIsSaving(true)
    await new Promise((r) => setTimeout(r, 600))
    setIsDirty(false)
    setIsSaving(false)
    setSaveSuccess(true)
    if (successTimer.current) clearTimeout(successTimer.current)
    successTimer.current = setTimeout(() => setSaveSuccess(false), 2000)
  }

  const tabs: { id: 'titles' | 'provider'; label: string }[] = [
    { id: 'titles',   label: 'Title rules' },
    { id: 'provider', label: 'Provider' },
  ]

  return (
    <>
      <Drawer
        isOpen={isOpen}
        onClose={handleClose}
        title="Contact Settings"
        subtitle="S3 · Configuration"
        accentColor="var(--s3)"
        footer={
          <button
            type="button"
            disabled={isSaving || !isDirty}
            onClick={() => void handleSave()}
            className="oc-btn oc-btn-sm"
            style={{
              backgroundColor: 'var(--s3)', borderColor: 'var(--s3)', color: '#fff',
              display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
              opacity: (!isDirty && !isSaving) ? 0.5 : 1, transition: 'opacity 200ms',
            }}
          >
            {isSaving ? <Spinner /> : saveSuccess ? '✓' : isDirty ? (
              <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: '#fbbf24', flexShrink: 0 }} />
            ) : null}
            {isSaving ? 'Saving…' : saveSuccess ? 'Saved' : 'Save changes'}
          </button>
        }
      >
        <div className="oc-drawer-tabs">
          {tabs.map((t) => (
            <button key={t.id} type="button" className="oc-drawer-tab"
              data-active={activeTab === t.id ? 'true' : 'false'}
              onClick={() => setActiveTab(t.id)}
            >{t.label}</button>
          ))}
        </div>

        {activeTab === 'titles' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
              Contacts are filtered to only people with titles that match these rules. One title or pattern per line.
            </p>
            <textarea
              value={titles}
              onChange={(e) => { setTitles(e.target.value); markDirty() }}
              className="oc-textarea"
              rows={20}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', resize: 'vertical' }}
            />
          </div>
        )}

        {activeTab === 'provider' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
              Select the contact data provider. Credits are consumed per company fetched.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {PROVIDERS.map((p) => (
                <label
                  key={p.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.875rem',
                    padding: '0.875rem 1rem', borderRadius: '0.75rem', cursor: 'pointer',
                    border: `1.5px solid ${provider === p.id ? 'var(--s3)' : 'var(--oc-border)'}`,
                    backgroundColor: provider === p.id ? 'var(--s3-bg)' : 'var(--oc-surface)',
                    transition: 'all 140ms',
                  }}
                >
                  <input type="radio" name="provider" value={p.id} checked={provider === p.id}
                    onChange={() => { setProvider(p.id); markDirty() }}
                    style={{ accentColor: 'var(--s3)', flexShrink: 0 }}
                  />
                  <div>
                    <div style={{ fontSize: '0.875rem', fontWeight: 600, color: provider === p.id ? 'var(--s3-text)' : 'var(--oc-text)' }}>{p.label}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>{p.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}
      </Drawer>

      <ConfirmDialog
        open={showUnsaved}
        title="Discard changes?"
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        confirmVariant="danger"
        onClose={() => setShowUnsaved(false)}
        onConfirm={() => { setShowUnsaved(false); setIsDirty(false); onClose() }}
      >
        You have unsaved changes. They will be lost if you close without saving.
      </ConfirmDialog>
    </>
  )
}
