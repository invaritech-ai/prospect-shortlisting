import { useState, useRef } from 'react'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'

const DEFAULT_RULES = `# Pages to include
- Homepage (/)
- About / Company (/about, /company, /who-we-are)
- Product / Platform (/product, /platform, /features, /solutions)
- Pricing (/pricing)

# Pages to exclude
- Blog posts and news articles
- Press releases and media kits
- Legal pages (terms, privacy, cookies)
- Login / signup pages
- Career / jobs pages`

const DEFAULT_INTENT = `You are classifying B2B SaaS companies for outbound sales targeting.

Classify as **Possible** if the company:
- Sells software or SaaS to other businesses (B2B)
- Has a clear enterprise or mid-market tier
- Operates in a segment we serve (HR, finance, analytics, productivity, dev tools)
- Has strong growth signals (funding, headcount, press mentions)

Classify as **Unknown** if you cannot determine B2B fit from the scraped content.

Classify as **Crap** if:
- Primarily B2C or consumer product
- No enterprise offering
- Irrelevant industry (gaming, media, e-commerce retail)
- Site is too thin or incomplete to judge`

function Spinner() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
      style={{ animation: 'spin 0.7s linear infinite', flexShrink: 0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  )
}

interface ScrapingSettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
}

export function ScrapingSettingsDrawer({ isOpen, onClose }: ScrapingSettingsDrawerProps) {
  const [rules, setRules]   = useState(DEFAULT_RULES)
  const [intent, setIntent] = useState(DEFAULT_INTENT)
  const [activeTab, setActiveTab] = useState<'pages' | 'intent'>('pages')

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

  const tabs: { id: 'pages' | 'intent'; label: string }[] = [
    { id: 'pages',  label: 'Page rules' },
    { id: 'intent', label: 'AI intent' },
  ]

  return (
    <>
      <Drawer
        isOpen={isOpen}
        onClose={handleClose}
        title="Scraping Settings"
        subtitle="S1 · Scraping"
        accentColor="var(--s1)"
        size="lg"
        footer={
          <button
            type="button"
            disabled={isSaving || !isDirty}
            onClick={() => void handleSave()}
            className="oc-btn oc-btn-sm"
            style={{
              backgroundColor: 'var(--s1)', borderColor: 'var(--s1)', color: '#fff',
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

        {activeTab === 'pages' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
              Define which pages to scrape and which to skip. Uses URL pattern matching.
            </p>
            <textarea
              value={rules}
              onChange={(e) => { setRules(e.target.value); markDirty() }}
              className="oc-textarea"
              rows={18}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', resize: 'vertical' }}
            />
          </div>
        )}

        {activeTab === 'intent' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
              High-level intent passed to the AI classifier. Defines what makes a company a fit.
            </p>
            <textarea
              value={intent}
              onChange={(e) => { setIntent(e.target.value); markDirty() }}
              className="oc-textarea"
              rows={18}
              style={{ fontFamily: 'var(--font-body)', fontSize: '0.8125rem', lineHeight: 1.6, resize: 'vertical' }}
            />
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
