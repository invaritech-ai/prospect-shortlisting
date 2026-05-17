import { useState, useEffect } from 'react'
import { Drawer } from '../ui/Drawer'
import type { CampaignRead } from '../../lib/types'

interface CampaignPanelProps {
  isOpen: boolean
  onClose: () => void
  editing?: CampaignRead | null
  onSave: (name: string, description: string) => Promise<void> | void
}

export function CampaignPanel({ isOpen, onClose, editing, onSave }: CampaignPanelProps) {
  const [name, setName]        = useState('')
  const [description, setDesc] = useState('')
  const [saving, setSaving]    = useState(false)
  const [error, setError]      = useState('')

  useEffect(() => {
    if (isOpen) {
      setName(editing?.name ?? '')
      setDesc(editing?.description ?? '')
      setError('')
    }
  }, [isOpen, editing])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Campaign name is required.'); return }
    setSaving(true)
    try {
      await onSave(name.trim(), description.trim())
      onClose()
    } catch {
      setError('Something went wrong. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const isEdit = Boolean(editing)

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? 'Edit Campaign' : 'New Campaign'}
      subtitle="Campaigns"
      size="md"
    >
      <form onSubmit={handleSubmit} style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

        {/* Name */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--oc-muted)' }}>
            Campaign name <span style={{ color: 'var(--oc-fail-text)' }}>*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => { setName(e.target.value); setError('') }}
            placeholder="e.g. Series B SaaS — Q2 2026"
            autoFocus
            style={{
              borderRadius: '0.625rem', border: `1px solid ${error ? 'var(--oc-fail-text)' : 'var(--oc-border)'}`,
              background: 'var(--oc-surface)', padding: '0.625rem 0.875rem',
              fontSize: '0.9375rem', color: 'var(--oc-text)', width: '100%',
              fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
              transition: 'border-color 160ms',
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--oc-accent)' }}
            onBlur={(e) => { e.currentTarget.style.borderColor = error ? 'var(--oc-fail-text)' : 'var(--oc-border)' }}
          />
          {error && <p style={{ fontSize: '0.8125rem', color: 'var(--oc-fail-text)', margin: 0 }}>{error}</p>}
        </div>

        {/* Description */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--oc-muted)' }}>
            Description <span style={{ fontSize: '0.6875rem', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional)</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="What is this campaign for?"
            rows={3}
            style={{
              borderRadius: '0.625rem', border: '1px solid var(--oc-border)',
              background: 'var(--oc-surface)', padding: '0.625rem 0.875rem',
              fontSize: '0.9375rem', color: 'var(--oc-text)', width: '100%',
              fontFamily: 'inherit', outline: 'none', resize: 'vertical',
              boxSizing: 'border-box', transition: 'border-color 160ms', lineHeight: 1.5,
            }}
            onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--oc-accent)' }}
            onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--oc-border)' }}
          />
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.625rem', justifyContent: 'flex-end', paddingTop: '0.5rem' }}>
          <button type="button" onClick={onClose} className="oc-btn oc-btn-secondary oc-btn-sm" disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="oc-btn oc-btn-primary oc-btn-sm" disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create campaign'}
          </button>
        </div>

      </form>
    </Drawer>
  )
}
