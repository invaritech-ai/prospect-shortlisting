import { useState, useRef } from 'react'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'

// ── Types & data ──────────────────────────────────────────────────────────────

type PromptEntry = { id: string; name: string; desc: string; body: string }

const LIBRARY: PromptEntry[] = [
  {
    id: 'b2b-saas',
    name: 'B2B SaaS Focus',
    desc: 'Standard B2B software filter — HR, finance, analytics, dev tools',
    body: `You are classifying B2B SaaS companies for outbound sales targeting.

Your task is to read the scraped website content and decide whether this company is a good target.

## Classification criteria

**Possible** — the company:
- Sells software or SaaS primarily to other businesses (B2B)
- Has a clear enterprise or mid-market offering
- Operates in a relevant segment: HR, finance, analytics, productivity, dev tools, security
- Shows strong growth signals (funding rounds, headcount growth, notable customers)
- Has a dedicated pricing page with business/enterprise tier

**Unknown** — when you cannot determine B2B fit clearly. Use this if:
- Content is too sparse or generic
- Industry is adjacent but unclear
- Mixed B2B/B2C signals

**Crap** — not a fit:
- Primarily B2C or consumer product
- No enterprise offering or clear business sales motion
- Irrelevant industry (gaming, media, e-commerce retail, local services)
- Marketing agency or service firm (not a software product)

## Output format
Return a JSON object with: verdict ("Possible"|"Unknown"|"Crap"), confidence (0-100), reasoning (1-2 sentences).`,
  },
  {
    id: 'enterprise',
    name: 'Enterprise Only',
    desc: 'Strict — must have 100+ employee customers and ACV signals',
    body: `You are classifying companies strictly for enterprise sales outreach.

Only classify as **Possible** if ALL of the following are true:
- Sells exclusively to enterprises (100+ employees)
- Has named enterprise customers or clearly stated enterprise tier
- Annual contract value signals above $10k/year
- Dedicated sales team or "contact sales" CTA on pricing

**Unknown** — borderline signals, insufficient data, or pricing not visible.

**Crap** — SMB, freemium, consumer, marketplace, or no clear revenue model.

## Output format
Return a JSON object with: verdict ("Possible"|"Unknown"|"Crap"), confidence (0-100), reasoning (1-2 sentences).`,
  },
  {
    id: 'startup',
    name: 'High-Growth Startups',
    desc: 'Series A–C SaaS with VC backing and strong growth signals',
    body: `You are identifying high-growth B2B startups for a venture-backed sales outreach campaign.

Target profile: Series A to Series C SaaS companies showing rapid expansion.

**Possible** — signs of:
- VC funding (Series A/B/C mentioned, notable investors named)
- Rapid headcount growth (many open roles, recent team hires)
- Category leadership language ("fastest growing", "trusted by X companies")
- B2B SaaS business model

**Unknown** — insufficient signals to confirm growth stage or funding.

**Crap** — bootstrapped lifestyle businesses, B2C, agencies, or clearly mature/slow-growth companies.

## Output format
Return a JSON object with: verdict ("Possible"|"Unknown"|"Crap"), confidence (0-100), reasoning (1-2 sentences).`,
  },
  {
    id: 'fintech',
    name: 'Fintech & Payments',
    desc: 'Financial infrastructure, payments, banking APIs, treasury tooling',
    body: `You are classifying B2B fintech companies for a targeted outreach campaign.

**Possible** — the company:
- Provides financial infrastructure, APIs, or tooling to other businesses
- Operates in: payments, banking-as-a-service, treasury, spend management, accounting automation, tax, lending infrastructure, compliance, or fraud
- Has a developer or business API product
- Clear B2B revenue model (subscription, transaction fee, platform fee)

**Unknown** — adjacent to fintech but unclear monetization, or mixed B2B/B2C.

**Crap** — consumer finance app, crypto speculation platform, insurance aggregator, or financial advisor firm.

## Output format
Return a JSON object with: verdict ("Possible"|"Unknown"|"Crap"), confidence (0-100), reasoning (1-2 sentences).`,
  },
]

const MODELS = [
  { id: 'openai/gpt-4o-mini',          label: 'GPT-4o Mini',   desc: 'Fast and cheap — good for high-volume runs' },
  { id: 'openai/gpt-4o',               label: 'GPT-4o',        desc: 'Accurate — better for nuanced classification' },
  { id: 'anthropic/claude-haiku-4-5',  label: 'Claude Haiku',  desc: 'Ultra-fast, very low cost' },
  { id: 'anthropic/claude-sonnet-4-6', label: 'Claude Sonnet', desc: 'Most accurate, best reasoning' },
]

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
      style={{ animation: 'spin 0.7s linear infinite', flexShrink: 0 }}>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
    </svg>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

interface AISettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
}

export function AISettingsDrawer({ isOpen, onClose }: AISettingsDrawerProps) {
  const [prompts, setPrompts]               = useState<PromptEntry[]>(LIBRARY)
  const [activePromptId, setActivePromptId] = useState('b2b-saas')
  const [selectedId, setSelectedId]         = useState('b2b-saas')
  const [model, setModel]                   = useState('openai/gpt-4o-mini')
  const [activeTab, setActiveTab]           = useState<'prompts' | 'model'>('prompts')

  // Dirty tracking — set of prompt ids with unsaved edits, plus model dirty flag
  const [dirtyIds, setDirtyIds]     = useState<Set<string>>(new Set())
  const [isModelDirty, setIsModelDirty] = useState(false)

  // Save state per prompt
  const [isSaving, setIsSaving]     = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const saveSuccessTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Confirm dialogs
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showUnsavedConfirm, setShowUnsavedConfirm] = useState(false)

  const selected = prompts.find((p) => p.id === selectedId) ?? prompts[0]
  const isSelectedActive = activePromptId === selectedId
  const isDirty = dirtyIds.has(selectedId)
  const anyDirty = dirtyIds.size > 0 || isModelDirty

  function handleClose() {
    if (anyDirty) { setShowUnsavedConfirm(true) } else { onClose() }
  }

  function discardAndClose() {
    setShowUnsavedConfirm(false)
    setDirtyIds(new Set())
    setIsModelDirty(false)
    onClose()
  }

  function updateSelected(patch: Partial<PromptEntry>) {
    setPrompts((prev) => prev.map((p) => p.id === selectedId ? { ...p, ...patch } : p))
    setDirtyIds((prev) => new Set([...prev, selectedId]))
    setSaveSuccess(false)
  }

  async function saveSelected() {
    setIsSaving(true)
    await new Promise((r) => setTimeout(r, 700))
    setDirtyIds((prev) => { const next = new Set(prev); next.delete(selectedId); return next })
    setIsSaving(false)
    setSaveSuccess(true)
    if (saveSuccessTimer.current) clearTimeout(saveSuccessTimer.current)
    saveSuccessTimer.current = setTimeout(() => setSaveSuccess(false), 2000)
  }

  async function saveModel() {
    setIsSaving(true)
    await new Promise((r) => setTimeout(r, 500))
    setIsModelDirty(false)
    setIsSaving(false)
    setSaveSuccess(true)
    if (saveSuccessTimer.current) clearTimeout(saveSuccessTimer.current)
    saveSuccessTimer.current = setTimeout(() => setSaveSuccess(false), 2000)
  }

  function addPrompt() {
    const id = `custom-${Date.now()}`
    const entry: PromptEntry = {
      id, name: 'New prompt',
      desc: 'Describe what this prompt targets',
      body: '# New classification prompt\n\nDescribe your classification criteria here.',
    }
    setPrompts((prev) => [...prev, entry])
    setSelectedId(id)
    setDirtyIds((prev) => new Set([...prev, id]))
  }

  function confirmDelete() {
    if (prompts.length <= 1) return
    const remaining = prompts.filter((p) => p.id !== selectedId)
    setPrompts(remaining)
    const fallback = remaining[0].id
    setSelectedId(fallback)
    if (activePromptId === selectedId) setActivePromptId(fallback)
    setDirtyIds((prev) => { const next = new Set(prev); next.delete(selectedId); return next })
    setShowDeleteConfirm(false)
  }

  return (
    <>
      <Drawer
        isOpen={isOpen}
        onClose={handleClose}
        title="AI Review Settings"
        subtitle="S2 · Configuration"
        accentColor="var(--s2)"
        size="lg"
        footer={
          activeTab === 'model' ? (
            <button
              type="button"
              disabled={isSaving}
              onClick={() => void saveModel()}
              className="oc-btn oc-btn-sm"
              style={{ backgroundColor: 'var(--s2)', borderColor: 'var(--s2)', color: '#fff', gap: '0.375rem', opacity: isSaving ? 0.7 : 1 }}
            >
              {isSaving ? <Spinner /> : saveSuccess ? '✓' : null}
              {isSaving ? 'Saving…' : saveSuccess ? 'Saved' : 'Save model'}
            </button>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={prompts.length <= 1}
                className="oc-btn oc-btn-sm oc-btn-ghost"
                style={{ color: 'var(--oc-fail-text)', opacity: prompts.length <= 1 ? 0.38 : 1 }}
              >
                Delete
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {!isSelectedActive && (
                  <button type="button" className="oc-btn oc-btn-sm oc-btn-secondary"
                    onClick={() => setActivePromptId(selectedId)}>
                    Set as active
                  </button>
                )}
                <button
                  type="button"
                  disabled={isSaving || !isDirty}
                  onClick={() => void saveSelected()}
                  className="oc-btn oc-btn-sm"
                  style={{
                    backgroundColor: 'var(--s2)', borderColor: 'var(--s2)', color: '#fff',
                    display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
                    opacity: (!isDirty && !isSaving) ? 0.5 : 1,
                    transition: 'opacity 200ms',
                  }}
                >
                  {isSaving ? <Spinner /> : saveSuccess ? '✓' : isDirty ? (
                    <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: '#fbbf24', flexShrink: 0 }} />
                  ) : null}
                  {isSaving ? 'Saving…' : saveSuccess ? 'Saved' : 'Save prompt'}
                </button>
              </div>
            </div>
          )
        }
      >
        {/* Tabs */}
        <div className="oc-drawer-tabs">
          {([
            { id: 'prompts', label: 'Prompt library' },
            { id: 'model',   label: 'Model' },
          ] as const).map((t) => (
            <button key={t.id} type="button" className="oc-drawer-tab"
              data-active={activeTab === t.id ? 'true' : 'false'}
              onClick={() => setActiveTab(t.id)}
            >{t.label}</button>
          ))}
        </div>

        {/* ── Prompt library ─────────────────────────────────────── */}
        {activeTab === 'prompts' && (
          <div style={{ display: 'flex', gap: 0, minHeight: 0 }}>

            {/* Left: prompt list */}
            <div style={{
              width: '210px', flexShrink: 0,
              display: 'flex', flexDirection: 'column', gap: '0.125rem',
              borderRight: '1px solid var(--oc-border)',
              paddingRight: '1rem', marginRight: '1.25rem',
              overflowY: 'auto',
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: '0.5rem', flexShrink: 0,
              }}>
                <span style={{ fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.18em', color: 'var(--oc-muted)' }}>
                  {prompts.length} prompts
                </span>
                <button
                  type="button"
                  onClick={addPrompt}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: '0.2rem',
                    padding: '0.2rem 0.5rem', borderRadius: '0.375rem',
                    border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                    fontSize: '0.6875rem', fontWeight: 700, color: 'var(--s2)',
                    cursor: 'pointer', transition: 'all 140ms',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--s2)'; e.currentTarget.style.background = 'var(--s2-bg)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)'; e.currentTarget.style.background = 'var(--oc-surface)' }}
                >
                  + New
                </button>
              </div>

              {prompts.map((p) => {
                const isSel = p.id === selectedId
                const isAct = p.id === activePromptId
                const hasDirt = dirtyIds.has(p.id)
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setSelectedId(p.id)}
                    style={{
                      width: '100%', textAlign: 'left',
                      padding: '0.5rem 0.625rem', borderRadius: '0.5rem',
                      border: `1.5px solid ${isSel ? 'var(--s2)' : 'transparent'}`,
                      background: isSel ? 'color-mix(in srgb, var(--s2) 8%, var(--oc-bg))' : 'transparent',
                      cursor: 'pointer', transition: 'all 140ms', flexShrink: 0,
                    }}
                    onMouseEnter={(e) => { if (!isSel) e.currentTarget.style.background = 'var(--oc-surface)' }}
                    onMouseLeave={(e) => { if (!isSel) e.currentTarget.style.background = 'transparent' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', marginBottom: '0.1875rem' }}>
                      <span style={{
                        width: '6px', height: '6px', borderRadius: '9999px', flexShrink: 0,
                        backgroundColor: isAct ? 'var(--s2)' : 'var(--oc-border)',
                        transition: 'background-color 200ms',
                      }} />
                      <span style={{
                        fontSize: '0.8125rem', fontWeight: isSel ? 700 : 500,
                        color: isSel ? 'var(--s2-text)' : 'var(--oc-text)',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
                      }}>
                        {p.name}
                      </span>
                      {hasDirt && (
                        <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: '#fbbf24', flexShrink: 0 }} title="Unsaved changes" />
                      )}
                    </div>
                    <span style={{
                      display: 'block', fontSize: '0.6875rem', color: 'var(--oc-muted)', lineHeight: 1.35,
                      paddingLeft: '0.9375rem',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {p.desc}
                    </span>
                    {isAct && (
                      <span style={{
                        display: 'inline-block', marginTop: '0.3rem', marginLeft: '0.9375rem',
                        fontSize: '0.5625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em',
                        color: 'var(--s2-text)', backgroundColor: 'var(--s2-bg)',
                        border: '1px solid color-mix(in srgb, var(--s2) 30%, var(--oc-border))',
                        padding: '0.125rem 0.375rem', borderRadius: '9999px',
                      }}>
                        Active
                      </span>
                    )}
                  </button>
                )
              })}
            </div>

            {/* Right: editor */}
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
              <input
                value={selected.name}
                onChange={(e) => updateSelected({ name: e.target.value })}
                className="oc-input"
                style={{ fontWeight: 700, fontSize: '1rem', fontFamily: 'var(--font-body)' }}
                placeholder="Prompt name"
              />
              <input
                value={selected.desc}
                onChange={(e) => updateSelected({ desc: e.target.value })}
                className="oc-input"
                style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', fontFamily: 'var(--font-body)' }}
                placeholder="Short description (shown in the list)"
              />
              {isSelectedActive && (
                <div style={{
                  display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
                  padding: '0.375rem 0.625rem', borderRadius: '0.375rem',
                  background: 'var(--s2-bg)',
                  border: '1px solid color-mix(in srgb, var(--s2) 25%, var(--oc-border))',
                  alignSelf: 'flex-start',
                }}>
                  <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: 'var(--s2)', flexShrink: 0 }} />
                  <span style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--s2-text)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
                    Currently active prompt
                  </span>
                </div>
              )}
              <textarea
                value={selected.body}
                onChange={(e) => updateSelected({ body: e.target.value })}
                className="oc-textarea"
                style={{ fontFamily: 'var(--font-body)', fontSize: '0.8125rem', lineHeight: 1.6, resize: 'none', flex: 1, minHeight: '320px' }}
              />
            </div>
          </div>
        )}

        {/* ── Model tab ─────────────────────────────────────────── */}
        {activeTab === 'model' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
              Choose the model used for AI classification. Faster models are cheaper; more capable models improve accuracy.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {MODELS.map((m) => (
                <label
                  key={m.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.875rem',
                    padding: '0.875rem 1rem', borderRadius: '0.75rem', cursor: 'pointer',
                    border: `1.5px solid ${model === m.id ? 'var(--s2)' : 'var(--oc-border)'}`,
                    backgroundColor: model === m.id ? 'var(--s2-bg)' : 'var(--oc-surface)',
                    transition: 'all 140ms',
                  }}
                >
                  <input
                    type="radio" name="model" value={m.id}
                    checked={model === m.id}
                    onChange={() => { setModel(m.id); setIsModelDirty(true); setSaveSuccess(false) }}
                    style={{ accentColor: 'var(--s2)', flexShrink: 0 }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.875rem', fontWeight: 600, color: model === m.id ? 'var(--s2-text)' : 'var(--oc-text)' }}>{m.label}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>{m.desc}</div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', color: 'var(--oc-muted)', flexShrink: 0 }}>{m.id}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </Drawer>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={showDeleteConfirm}
        title={`Delete "${selected.name}"?`}
        confirmLabel="Delete"
        cancelLabel="Keep"
        confirmVariant="danger"
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={confirmDelete}
      >
        This prompt will be permanently removed from the library. This can't be undone.
      </ConfirmDialog>

      {/* Unsaved changes confirmation */}
      <ConfirmDialog
        open={showUnsavedConfirm}
        title="Discard changes?"
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        confirmVariant="danger"
        onClose={() => setShowUnsavedConfirm(false)}
        onConfirm={discardAndClose}
      >
        You have unsaved changes. They will be lost if you close without saving.
      </ConfirmDialog>
    </>
  )
}
