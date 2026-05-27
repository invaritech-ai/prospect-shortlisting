import { useEffect, useMemo, useState } from 'react'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import {
  ApiError,
  createDecisionSettings,
  deleteDecisionSettings,
  listDecisionSettings,
  updateDecisionSettings,
} from '../../../lib/api'
import type { DecisionModelId, DecisionSettingsRead } from '../../../lib/types'

const NEW_ID = '__new__'

const MODELS: Array<{ id: DecisionModelId; label: string; desc: string }> = [
  { id: 'inclusionai/ring-2.6-1t', label: 'Ring 2.6 1T', desc: 'Long-context model for deep classification' },
  { id: 'ibm-granite/granite-4.1-8b', label: 'Granite 4.1 8B', desc: 'Balanced speed and reliability' },
  { id: 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', label: 'Nemotron 30B (Free)', desc: 'Reasoning-focused free model' },
  { id: 'deepseek/deepseek-v4-flash', label: 'DeepSeek V4 Flash', desc: 'Fast responses for larger volumes' },
  { id: 'inclusionai/ling-2.6-1t', label: 'Ling 2.6 1T', desc: 'Alternative long-context inclusion model' },
  { id: 'google/gemma-4-26b-a4b-it:free', label: 'Gemma 4 26B (Free)', desc: 'Free, instruction-tuned medium model' },
  { id: 'google/gemma-4-31b-it:free', label: 'Gemma 4 31B (Free)', desc: 'Free, larger Gemma model' },
]

interface AISettingsDrawerProps {
  isOpen: boolean
  onClose: () => void
  campaignId: string
}

export function AISettingsDrawer({ isOpen, onClose, campaignId }: AISettingsDrawerProps) {
  const [activeTab, setActiveTab] = useState<'prompts' | 'model'>('prompts')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  const [prompts, setPrompts] = useState<DecisionSettingsRead[]>([])
  const [selectedId, setSelectedId] = useState<string>(NEW_ID)

  const [name, setName] = useState('')
  const [instructionText, setInstructionText] = useState('')
  const [model, setModel] = useState<DecisionModelId>('inclusionai/ring-2.6-1t')

  const [dirtyPrompt, setDirtyPrompt] = useState(false)
  const [dirtyModel, setDirtyModel] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showUnsavedConfirm, setShowUnsavedConfirm] = useState(false)

  const selected = useMemo(
    () => prompts.find((p) => p.id === selectedId) ?? null,
    [prompts, selectedId],
  )

  const activePromptId = useMemo(
    () => prompts.find((p) => p.is_active)?.id ?? null,
    [prompts],
  )

  const anyDirty = dirtyPrompt || dirtyModel

  useEffect(() => {
    if (!isOpen || !campaignId) return
    let cancelled = false
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const rows = await listDecisionSettings(campaignId, { limit: 100, offset: 0 })
        if (cancelled) return
        setPrompts(rows.items)
        const initial = rows.items.find((p) => p.is_active) ?? rows.items[0] ?? null
        if (initial) {
          setSelectedId(initial.id)
          setName(initial.name)
          setInstructionText(initial.instruction_text)
          setModel(initial.model)
        } else {
          setSelectedId(NEW_ID)
          setName('')
          setInstructionText('')
          setModel('inclusionai/ring-2.6-1t')
        }
        setDirtyPrompt(false)
        setDirtyModel(false)
      } catch (e) {
        const detail = e instanceof ApiError ? String(e.detail) : 'Failed to load decision settings.'
        setError(detail)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [isOpen, campaignId])

  function selectPrompt(id: string) {
    if (anyDirty) {
      setShowUnsavedConfirm(true)
      return
    }
    if (id === NEW_ID) {
      setSelectedId(NEW_ID)
      setName('')
      setInstructionText('')
      setModel('inclusionai/ring-2.6-1t')
      setDirtyPrompt(false)
      setDirtyModel(false)
      return
    }
    const row = prompts.find((p) => p.id === id)
    if (!row) return
    setSelectedId(row.id)
    setName(row.name)
    setInstructionText(row.instruction_text)
    setModel(row.model)
    setDirtyPrompt(false)
    setDirtyModel(false)
    setError(null)
  }

  async function savePrompt() {
    if (!name.trim() || !instructionText.trim()) {
      setError('Prompt name and instruction text are required.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (selectedId === NEW_ID) {
        const created = await createDecisionSettings({
          campaign_id: campaignId,
          name: name.trim(),
          instruction_text: instructionText.trim(),
          model,
          is_active: activePromptId === null,
        })
        const next = [created, ...prompts]
        setPrompts(next)
        setSelectedId(created.id)
      } else {
        const updated = await updateDecisionSettings(selectedId, {
          name: name.trim(),
          instruction_text: instructionText.trim(),
          model,
        })
        setPrompts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
      }
      setDirtyPrompt(false)
      setDirtyModel(false)
      setSaveSuccess(true)
      window.setTimeout(() => setSaveSuccess(false), 1500)
    } catch (e) {
      const detail = e instanceof ApiError ? String(e.detail) : 'Failed to save prompt.'
      setError(detail)
    } finally {
      setSaving(false)
    }
  }

  async function saveModelOnly() {
    if (!selected || selectedId === NEW_ID) {
      setError('Save prompt first before saving model.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const updated = await updateDecisionSettings(selected.id, { model })
      setPrompts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
      setDirtyModel(false)
      setSaveSuccess(true)
      window.setTimeout(() => setSaveSuccess(false), 1500)
    } catch (e) {
      const detail = e instanceof ApiError ? String(e.detail) : 'Failed to save model.'
      setError(detail)
    } finally {
      setSaving(false)
    }
  }

  async function activateSelected() {
    if (!selected || selectedId === NEW_ID) return
    setSaving(true)
    setError(null)
    try {
      const updated = await updateDecisionSettings(selected.id, { is_active: true })
      setPrompts((prev) => prev.map((p) => ({ ...p, is_active: p.id === updated.id })))
    } catch (e) {
      const detail = e instanceof ApiError ? String(e.detail) : 'Failed to activate prompt.'
      setError(detail)
    } finally {
      setSaving(false)
    }
  }

  async function confirmDelete() {
    if (!selected || selectedId === NEW_ID) return
    setSaving(true)
    setError(null)
    try {
      await deleteDecisionSettings(selected.id)
      const next = prompts.filter((p) => p.id !== selected.id)
      setPrompts(next)
      const fallback = next.find((p) => p.is_active) ?? next[0] ?? null
      if (fallback) {
        setSelectedId(fallback.id)
        setName(fallback.name)
        setInstructionText(fallback.instruction_text)
        setModel(fallback.model)
      } else {
        setSelectedId(NEW_ID)
        setName('')
        setInstructionText('')
        setModel('inclusionai/ring-2.6-1t')
      }
      setDirtyPrompt(false)
      setDirtyModel(false)
      setShowDeleteConfirm(false)
    } catch (e) {
      const detail = e instanceof ApiError ? String(e.detail) : 'Failed to delete prompt.'
      setError(detail)
    } finally {
      setSaving(false)
    }
  }

  function handleClose() {
    if (anyDirty) {
      setShowUnsavedConfirm(true)
      return
    }
    onClose()
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
              disabled={saving || !dirtyModel}
              onClick={() => void saveModelOnly()}
              className="oc-btn oc-btn-sm"
              style={{ backgroundColor: 'var(--s2)', borderColor: 'var(--s2)', color: '#fff', opacity: saving || !dirtyModel ? 0.65 : 1 }}
            >
              {saving ? 'Saving…' : saveSuccess ? 'Saved' : 'Save model'}
            </button>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                disabled={saving || !selected || selectedId === NEW_ID}
                className="oc-btn oc-btn-sm oc-btn-ghost"
                style={{ color: 'var(--oc-fail-text)', opacity: saving || !selected || selectedId === NEW_ID ? 0.4 : 1 }}
              >
                Delete
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {selected && selectedId !== NEW_ID && !selected.is_active && (
                  <button type="button" className="oc-btn oc-btn-sm oc-btn-secondary" onClick={() => void activateSelected()} disabled={saving}>
                    Set as active
                  </button>
                )}
                <button
                  type="button"
                  disabled={saving || !dirtyPrompt}
                  onClick={() => void savePrompt()}
                  className="oc-btn oc-btn-sm"
                  style={{ backgroundColor: 'var(--s2)', borderColor: 'var(--s2)', color: '#fff', opacity: saving || !dirtyPrompt ? 0.65 : 1 }}
                >
                  {saving ? 'Saving…' : saveSuccess ? 'Saved' : selectedId === NEW_ID ? 'Create prompt' : 'Save prompt'}
                </button>
              </div>
            </div>
          )
        }
      >
        <div className="oc-drawer-tabs">
          {([
            { id: 'prompts', label: 'Prompt library' },
            { id: 'model', label: 'Model' },
          ] as const).map((t) => (
            <button key={t.id} type="button" className="oc-drawer-tab" data-active={activeTab === t.id ? 'true' : 'false'} onClick={() => setActiveTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="oc-callout-fail" style={{ marginBottom: '0.75rem' }}>{error}</div>
        )}

        {activeTab === 'prompts' && (
          <div style={{ display: 'flex', gap: 0, minHeight: 0 }}>
            <div style={{ width: '230px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '0.125rem', borderRight: '1px solid var(--oc-border)', paddingRight: '1rem', marginRight: '1.25rem', overflowY: 'auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.18em', color: 'var(--oc-muted)' }}>
                  {prompts.length} prompts
                </span>
                <button type="button" onClick={() => selectPrompt(NEW_ID)} className="oc-btn oc-btn-sm oc-btn-ghost">+ New</button>
              </div>

              {loading ? <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>Loading…</div> : null}

              {prompts.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => selectPrompt(p.id)}
                  style={{
                    width: '100%', textAlign: 'left', padding: '0.5rem 0.625rem', borderRadius: '0.5rem',
                    border: `1.5px solid ${p.id === selectedId ? 'var(--s2)' : 'transparent'}`,
                    background: p.id === selectedId ? 'color-mix(in srgb, var(--s2) 8%, var(--oc-bg))' : 'transparent',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', marginBottom: '0.1875rem' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: p.is_active ? 'var(--s2)' : 'var(--oc-border)' }} />
                    <span style={{ fontSize: '0.8125rem', fontWeight: p.id === selectedId ? 700 : 500, color: p.id === selectedId ? 'var(--s2-text)' : 'var(--oc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                      {p.name}
                    </span>
                  </div>
                  <span style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--oc-muted)', lineHeight: 1.35, paddingLeft: '0.9375rem' }}>
                    {new Date(p.created_at).toLocaleString()}
                  </span>
                </button>
              ))}
            </div>

            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
              <input
                value={name}
                onChange={(e) => { setName(e.target.value); setDirtyPrompt(true); setSaveSuccess(false) }}
                className="oc-input"
                style={{ fontWeight: 700, fontSize: '1rem', fontFamily: 'var(--font-body)' }}
                placeholder="Prompt name"
              />
              {selected?.is_active && (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', padding: '0.375rem 0.625rem', borderRadius: '0.375rem', background: 'var(--s2-bg)', border: '1px solid color-mix(in srgb, var(--s2) 25%, var(--oc-border))', alignSelf: 'flex-start' }}>
                  <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: 'var(--s2)' }} />
                  <span style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--s2-text)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
                    Currently active prompt
                  </span>
                </div>
              )}
              <textarea
                value={instructionText}
                onChange={(e) => { setInstructionText(e.target.value); setDirtyPrompt(true); setSaveSuccess(false) }}
                className="oc-textarea"
                style={{ fontFamily: 'var(--font-body)', fontSize: '0.8125rem', lineHeight: 1.6, resize: 'none', flex: 1, minHeight: '360px' }}
              />
            </div>
          </div>
        )}

        {activeTab === 'model' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--oc-muted)', lineHeight: 1.55 }}>
              Choose the model used for AI classification.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {MODELS.map((m) => (
                <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '0.875rem', padding: '0.875rem 1rem', borderRadius: '0.75rem', cursor: 'pointer', border: `1.5px solid ${model === m.id ? 'var(--s2)' : 'var(--oc-border)'}`, backgroundColor: model === m.id ? 'var(--s2-bg)' : 'var(--oc-surface)' }}>
                  <input
                    type="radio"
                    name="model"
                    value={m.id}
                    checked={model === m.id}
                    onChange={() => { setModel(m.id); setDirtyModel(true); setDirtyPrompt(selectedId === NEW_ID ? true : dirtyPrompt); setSaveSuccess(false) }}
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

      <ConfirmDialog
        open={showDeleteConfirm}
        title={`Delete "${name || 'this prompt'}"?`}
        confirmLabel="Delete"
        cancelLabel="Keep"
        confirmVariant="danger"
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={() => void confirmDelete()}
      >
        This prompt will be permanently removed from the library. This can't be undone.
      </ConfirmDialog>

      <ConfirmDialog
        open={showUnsavedConfirm}
        title="Discard changes?"
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        confirmVariant="danger"
        onClose={() => setShowUnsavedConfirm(false)}
        onConfirm={() => {
          setShowUnsavedConfirm(false)
          setDirtyPrompt(false)
          setDirtyModel(false)
          onClose()
        }}
      >
        You have unsaved changes. They will be lost if you close without saving.
      </ConfirmDialog>
    </>
  )
}
