import { useState, useRef, useEffect } from 'react'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import { getScrapeSettings, saveScrapeSettings } from '../../../lib/api'

const DEFAULT_RULES = `# Pages to include
- Homepage (/)
- About / Company (/about, /company, /who-we-are)
- Product / Platform (/product, /platform, /features, /solutions)
- Pricing (/pricing)
- Contact (/contact)
- Team / Leadership (/team, /leadership, /about/team)

# Pages to exclude
- Blog posts and news articles
- Press releases and media kits
- Legal pages (terms, privacy, cookies)
- Login / signup pages
- Career / jobs pages`

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
  campaignId: string
}

export function ScrapingSettingsDrawer({ isOpen, onClose, campaignId }: ScrapingSettingsDrawerProps) {
  const [rules, setRules]             = useState(DEFAULT_RULES)
  const [isDirty, setIsDirty]         = useState(false)
  const [isSaving, setIsSaving]       = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [showUnsaved, setShowUnsaved] = useState(false)
  const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load existing settings when drawer opens
  useEffect(() => {
    if (!isOpen) return
    getScrapeSettings(campaignId).then((settings) => {
      if (settings?.instruction_text) {
        setRules(settings.instruction_text)
      }
    }).catch(() => { /* use defaults */ })
    setIsDirty(false)
    setSaveSuccess(false)
  }, [isOpen, campaignId])

  function markDirty() { setIsDirty(true); setSaveSuccess(false) }

  function handleClose() {
    if (isDirty) { setShowUnsaved(true) } else { onClose() }
  }

  async function handleSave() {
    setIsSaving(true)
    try {
      await saveScrapeSettings(campaignId, rules)
      setIsDirty(false)
      setSaveSuccess(true)
      if (successTimer.current) clearTimeout(successTimer.current)
      successTimer.current = setTimeout(() => setSaveSuccess(false), 2000)
    } catch {
      // leave dirty so user can retry
    } finally {
      setIsSaving(false)
    }
  }

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
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
          <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
            Define which pages to scrape and which to skip. These rules apply to all future scrape batches in this campaign.
          </p>
          <textarea
            value={rules}
            onChange={(e) => { setRules(e.target.value); markDirty() }}
            className="oc-textarea"
            rows={18}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', resize: 'vertical' }}
          />
        </div>
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
