import { useState, useRef, useEffect } from 'react'
import type { ScrapeSettingsRead } from '../../../lib/types'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import {
  listScrapeSettings,
  saveScrapeSettings,
} from '../../../lib/api'
import { parseApiError } from '../../../lib/utils'

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
  const [selectedSettings, setSelectedSettings] = useState<ScrapeSettingsRead | null>(null)
  const [history, setHistory]         = useState<ScrapeSettingsRead[]>([])
  const [isDirty, setIsDirty]         = useState(false)
  const [isLoading, setIsLoading]     = useState(false)
  const [isSaving, setIsSaving]       = useState(false)
  const [error, setError]             = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [showUnsaved, setShowUnsaved] = useState(false)
  const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  async function loadSettings() {
    setIsLoading(true)
    setError(null)
    try {
      const allSettings = await listScrapeSettings(campaignId)
      const latest = allSettings.items[0] ?? null
      setSelectedSettings(latest)
      setHistory(allSettings.items)
      setRules(latest?.instruction_text || DEFAULT_RULES)
    } catch (err) {
      setError(parseApiError(err))
      setRules(DEFAULT_RULES)
      setSelectedSettings(null)
      setHistory([])
    } finally {
      setIsLoading(false)
    }
  }

  // Load existing settings when drawer opens
  useEffect(() => {
    if (!isOpen) return
    void loadSettings()
    setIsDirty(false)
    setSaveSuccess(false)
  }, [isOpen, campaignId])

  function markDirty() { setIsDirty(true); setSaveSuccess(false) }

  function handleClose() {
    if (isDirty) { setShowUnsaved(true) } else { onClose() }
  }

  async function handleSave() {
    setIsSaving(true)
    setError(null)
    try {
      const saved = await saveScrapeSettings(campaignId, rules)
      setSelectedSettings(saved)
      const allSettings = await listScrapeSettings(campaignId)
      setHistory(allSettings.items)
      setIsDirty(false)
      setSaveSuccess(true)
      if (successTimer.current) clearTimeout(successTimer.current)
      successTimer.current = setTimeout(() => setSaveSuccess(false), 2000)
    } catch (err) {
      setError(parseApiError(err))
      // leave dirty so user can retry
    } finally {
      setIsSaving(false)
    }
  }

  function loadHistoryItem(item: ScrapeSettingsRead) {
    setSelectedSettings(item)
    setRules(item.instruction_text || DEFAULT_RULES)
    setIsDirty(false)
    setSaveSuccess(false)
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
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
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
              {isSaving ? 'Saving…' : saveSuccess ? 'Saved' : history.length > 0 ? 'Save new version' : 'Save settings'}
            </button>
          </div>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
          {error && (
            <div style={{ padding: '0.75rem 1rem', borderRadius: '0.5rem', background: 'var(--oc-fail-bg)', color: 'var(--oc-fail-text)', fontSize: '0.8125rem' }}>
              {error}
            </div>
          )}
          {isLoading && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', color: 'var(--oc-muted)', fontSize: '0.8125rem' }}>
              <Spinner /> Loading settings…
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.75rem', alignItems: 'center' }}>
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
              Define which pages to scrape and which to skip. These rules apply to future scrape batches in this campaign.
            </p>
          </div>
          <textarea
            value={rules}
            onChange={(e) => { setRules(e.target.value); markDirty() }}
            className="oc-textarea"
            rows={18}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', resize: 'vertical' }}
          />
          {history.length > 0 && (
            <div style={{ borderTop: '1px solid var(--oc-border)', paddingTop: '0.875rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--oc-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>
                Versions
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                {history.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => loadHistoryItem(item)}
                    className="oc-btn oc-btn-secondary oc-btn-sm"
                    style={{
                      justifyContent: 'space-between',
                      fontFamily: 'var(--font-mono)',
                      borderColor: selectedSettings?.id === item.id ? 'var(--s1)' : undefined,
                      color: selectedSettings?.id === item.id ? 'var(--s1)' : undefined,
                      opacity: selectedSettings?.id === item.id ? 1 : 0.82,
                    }}
                  >
                    <span>{new Date(item.created_at).toLocaleString()}</span>
                    {history[0]?.id === item.id && <span>latest</span>}
                  </button>
                ))}
              </div>
            </div>
          )}
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
