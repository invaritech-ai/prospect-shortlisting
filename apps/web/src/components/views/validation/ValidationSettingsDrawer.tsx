import { useState, useRef } from 'react'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'

function Spinner() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
      style={{ animation: 'spin 0.7s linear infinite', flexShrink: 0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  )
}

interface ValidationSettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
}

export function ValidationSettingsDrawer({ isOpen, onClose }: ValidationSettingsDrawerProps) {
  const [batchSize, setBatchSize]       = useState('100')
  const [includeRisky, setIncludeRisky] = useState(true)
  const [activeTab, setActiveTab]       = useState<'config' | 'status'>('config')

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

  const tabs: { id: 'config' | 'status'; label: string }[] = [
    { id: 'config', label: 'Configuration' },
    { id: 'status', label: 'API status' },
  ]

  return (
    <>
      <Drawer
        isOpen={isOpen}
        onClose={handleClose}
        title="Validation Settings"
        subtitle="S4 · ZeroBounce"
        accentColor="var(--s5)"
        footer={
          activeTab === 'config' ? (
            <button
              type="button"
              disabled={isSaving || !isDirty}
              onClick={() => void handleSave()}
              className="oc-btn oc-btn-sm"
              style={{
                backgroundColor: 'var(--s5)', borderColor: 'var(--s5)', color: '#fff',
                display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
                opacity: (!isDirty && !isSaving) ? 0.5 : 1, transition: 'opacity 200ms',
              }}
            >
              {isSaving ? <Spinner /> : saveSuccess ? '✓' : isDirty ? (
                <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: '#fbbf24', flexShrink: 0 }} />
              ) : null}
              {isSaving ? 'Saving…' : saveSuccess ? 'Saved' : 'Save settings'}
            </button>
          ) : undefined
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

        {activeTab === 'config' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div className="oc-form-field">
              <label className="oc-form-label">Batch size per run</label>
              <select value={batchSize}
                onChange={(e) => { setBatchSize(e.target.value); markDirty() }}
                className="oc-select"
              >
                <option value="50">50 emails</option>
                <option value="100">100 emails</option>
                <option value="250">250 emails</option>
                <option value="500">500 emails</option>
              </select>
              <p className="oc-form-hint">How many emails to validate per batch job. Larger batches are faster but consume more credits at once.</p>
            </div>

            <div style={{
              display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem',
              padding: '0.875rem 1rem', borderRadius: '0.75rem',
              border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
            }}>
              <div>
                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--oc-text)' }}>Include risky emails in export</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>Catch-all and role addresses will be included in the final list</div>
              </div>
              <label style={{ position: 'relative', display: 'inline-flex', width: '40px', height: '22px', flexShrink: 0, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={includeRisky}
                  onChange={(e) => { setIncludeRisky(e.target.checked); markDirty() }}
                  style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
                />
                <span style={{
                  position: 'absolute', inset: 0, borderRadius: '9999px',
                  backgroundColor: includeRisky ? 'var(--s5)' : 'var(--oc-border)',
                  transition: 'background-color 200ms',
                }}>
                  <span style={{
                    position: 'absolute', top: '3px',
                    left: includeRisky ? '21px' : '3px',
                    width: '16px', height: '16px', borderRadius: '9999px',
                    backgroundColor: '#fff',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                    transition: 'left 200ms',
                  }} />
                </span>
              </label>
            </div>
          </div>
        )}

        {activeTab === 'status' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{
              padding: '1.25rem 1.375rem', borderRadius: '0.875rem',
              border: '1.5px solid color-mix(in srgb, var(--s5) 20%, var(--oc-border))',
              background: 'var(--s5-bg)',
            }}>
              <div style={{ fontSize: '0.625rem', fontWeight: 700, color: 'var(--s5-text)', textTransform: 'uppercase', letterSpacing: '0.18em', marginBottom: '0.5rem' }}>Credits remaining</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '2.5rem', fontWeight: 900, color: 'var(--s5)', lineHeight: 1 }}>15,000</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--s5-text)', marginTop: '0.375rem', opacity: 0.75 }}>≈ 150 batches of 100</div>
            </div>

            <div style={{
              display: 'flex', alignItems: 'center', gap: '0.625rem',
              padding: '0.875rem 1rem', borderRadius: '0.75rem',
              border: '1.5px solid color-mix(in srgb, var(--oc-success-text) 20%, var(--oc-border))',
              background: 'var(--oc-success-bg)',
            }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '9999px', backgroundColor: 'var(--oc-success-text)', flexShrink: 0 }} />
              <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--oc-success-text)' }}>Connected to ZeroBounce</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              {[
                { label: 'Validated today', value: '243' },
                { label: 'Success rate',    value: '96.3%' },
                { label: 'Avg response',    value: '1.2s' },
                { label: 'Last used',       value: '4m ago' },
              ].map((s) => (
                <div key={s.label} style={{ padding: '0.875rem 1rem', borderRadius: '0.625rem', border: '1px solid var(--oc-border)', background: 'var(--oc-surface)' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.25rem', fontWeight: 800, color: 'var(--oc-text)', lineHeight: 1 }}>{s.value}</div>
                  <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', marginTop: '0.3rem', fontWeight: 500 }}>{s.label}</div>
                </div>
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
