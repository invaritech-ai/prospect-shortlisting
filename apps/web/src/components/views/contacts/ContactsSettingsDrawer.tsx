import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from 'react'
import { getEmailFetchCriteria, saveEmailFetchCriteria } from '../../../lib/api'
import type { EmailFetchCriteriaRead } from '../../../lib/types'
import { parseApiError } from '../../../lib/utils'
import { Drawer } from '../../ui/Drawer'
import { ConfirmDialog } from '../../ui/ConfirmDialog'
import { Loader2, X } from 'lucide-react'

const DEFAULT_INCLUDE_RULES = [
  'CEO',
  'Chief Executive Officer',
  'Founder',
  'Co-founder',
  'Owner',
  'President',
  'Managing Director',
  'CTO',
  'Chief Technology Officer',
  'VP Sales',
  'Head of Sales',
  'Sales Director',
  'Marketing Director',
  'Head of Marketing',
]

const DEFAULT_EXCLUDE_RULES = [
  'Assistant',
  'Executive Assistant',
  'Intern',
  'Consultant',
  'Advisor',
  'Recruiter',
  'Talent Acquisition',
  'Human Resources',
  'Student',
]

function Spinner() {
  return <Loader2 size={13} style={{ animation: 'spin 0.7s linear infinite', flexShrink: 0 }} />
}

function normalizeRule(value: string): string {
  return value.trim().replace(/\s+/g, ' ')
}

function cleanRules(values: string[]): string[] {
  const seen = new Set<string>()
  const rules: string[] = []
  for (const raw of values) {
    const value = normalizeRule(raw)
    if (!value || value.startsWith('#')) continue
    const key = value.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    rules.push(value)
  }
  return rules
}

function parseRulesFromText(text: string): string[] {
  return cleanRules(text.split(/[\n,]+/))
}

function rulesEqual(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index])
}

interface RuleChipEditorProps {
  label: string
  rules: string[]
  draft: string
  placeholder: string
  tone: 'include' | 'exclude'
  disabled?: boolean
  onDraftChange: (value: string) => void
  onRulesChange: (rules: string[]) => void
  onDirty: () => void
}

function RuleChipEditor({
  label,
  rules,
  draft,
  placeholder,
  tone,
  disabled = false,
  onDraftChange,
  onRulesChange,
  onDirty,
}: RuleChipEditorProps) {
  const accent = tone === 'include' ? 'var(--s3)' : 'var(--oc-warn-text)'
  const bg = tone === 'include' ? 'var(--s3-bg)' : 'var(--oc-warn-bg)'

  function applyRules(nextRules: string[]) {
    const cleaned = cleanRules(nextRules)
    if (!rulesEqual(cleaned, rules)) {
      onRulesChange(cleaned)
      onDirty()
    }
  }

  function addDraftRules() {
    const additions = parseRulesFromText(draft)
    if (additions.length === 0) return
    applyRules([...rules, ...additions])
    onDraftChange('')
  }

  function removeRule(index: number) {
    applyRules(rules.filter((_, i) => i !== index))
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      addDraftRules()
      return
    }
    if (e.key === 'Backspace' && draft.length === 0 && rules.length > 0) {
      e.preventDefault()
      removeRule(rules.length - 1)
    }
  }

  function handlePaste(e: ClipboardEvent<HTMLInputElement>) {
    const pasted = e.clipboardData.getData('text')
    if (!/[\n,]/.test(pasted)) return
    e.preventDefault()
    const additions = parseRulesFromText(pasted)
    if (additions.length === 0) return
    applyRules([...rules, ...additions])
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
        <span style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--oc-text)' }}>{label}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>
          {rules.length}
        </span>
      </div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.375rem',
          alignItems: 'center',
          minHeight: '92px',
          borderRadius: '0.625rem',
          border: `1.5px solid color-mix(in srgb, ${accent} 24%, var(--oc-border))`,
          background: 'var(--oc-surface)',
          padding: '0.625rem',
        }}
      >
        {rules.map((rule, index) => (
          <span
            key={`${rule}:${index}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem',
              maxWidth: '100%',
              borderRadius: '9999px',
              border: `1px solid color-mix(in srgb, ${accent} 38%, var(--oc-border))`,
              background: bg,
              color: accent,
              padding: '0.25rem 0.375rem 0.25rem 0.625rem',
              fontSize: '0.75rem',
              fontWeight: 650,
            }}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{rule}</span>
            <button
              type="button"
              aria-label={`Remove ${rule}`}
              disabled={disabled}
              onClick={() => removeRule(index)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '18px',
                height: '18px',
                borderRadius: '9999px',
                border: 'none',
                background: 'transparent',
                color: accent,
                cursor: disabled ? 'not-allowed' : 'pointer',
                padding: 0,
                opacity: disabled ? 0.45 : 0.8,
              }}
            >
              <X size={12} strokeWidth={2.5} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          disabled={disabled}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={rules.length === 0 ? placeholder : 'Add title...'}
          style={{
            flex: '1 1 160px',
            minWidth: '140px',
            border: 'none',
            outline: 'none',
            background: 'transparent',
            color: 'var(--oc-text)',
            font: 'inherit',
            fontSize: '0.8125rem',
            padding: '0.25rem',
          }}
        />
      </div>
    </section>
  )
}

interface ContactsSettingsDrawerProps {
  campaignId: string
  isOpen: boolean
  onClose: () => void
  onSaved: (criteria: EmailFetchCriteriaRead) => void
}

export function ContactsSettingsDrawer({ campaignId, isOpen, onClose, onSaved }: ContactsSettingsDrawerProps) {
  const [includeRules, setIncludeRules] = useState<string[]>(DEFAULT_INCLUDE_RULES)
  const [excludeRules, setExcludeRules] = useState<string[]>(DEFAULT_EXCLUDE_RULES)
  const [includeDraft, setIncludeDraft] = useState('')
  const [excludeDraft, setExcludeDraft] = useState('')
  const [isDirty, setIsDirty] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [error, setError] = useState('')
  const [showUnsaved, setShowUnsaved] = useState(false)
  const successTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setIsLoading(true)
    setError('')
    void getEmailFetchCriteria(campaignId)
      .then((criteria) => {
        if (cancelled) return
        const shouldUseDefaults = !criteria.id || criteria.include_titles.length === 0
        setIncludeRules(shouldUseDefaults ? DEFAULT_INCLUDE_RULES : cleanRules(criteria.include_titles))
        setExcludeRules(!criteria.id ? DEFAULT_EXCLUDE_RULES : cleanRules(criteria.exclude_titles))
        setIncludeDraft('')
        setExcludeDraft('')
        setIsDirty(shouldUseDefaults)
        onSaved(criteria)
      })
      .catch((err) => {
        if (!cancelled) setError(parseApiError(err))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => { cancelled = true }
  }, [campaignId, isOpen, onSaved])

  function markDirty() {
    setIsDirty(true)
    setSaveSuccess(false)
    setError('')
  }

  function handleClose() {
    if (isDirty || includeDraft.trim() || excludeDraft.trim()) { setShowUnsaved(true) } else { onClose() }
  }

  async function handleSave() {
    const finalIncludeRules = cleanRules([...includeRules, ...parseRulesFromText(includeDraft)])
    const finalExcludeRules = cleanRules([...excludeRules, ...parseRulesFromText(excludeDraft)])
    setIsSaving(true)
    setError('')
    try {
      const criteria = await saveEmailFetchCriteria({
        campaign_id: campaignId,
        include_titles: finalIncludeRules,
        exclude_titles: finalExcludeRules,
        target_contacts_per_company: 3,
      })
      setIncludeRules(finalIncludeRules)
      setExcludeRules(finalExcludeRules)
      setIncludeDraft('')
      setExcludeDraft('')
      setIsDirty(false)
      setSaveSuccess(true)
      onSaved(criteria)
      if (successTimer.current) clearTimeout(successTimer.current)
      successTimer.current = setTimeout(() => setSaveSuccess(false), 2000)
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setIsSaving(false)
    }
  }

  const savingDisabled = isSaving || isLoading || (!isDirty && !includeDraft.trim() && !excludeDraft.trim()) || includeRules.length === 0

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
            disabled={savingDisabled}
            onClick={() => void handleSave()}
            className="oc-btn oc-btn-sm"
            style={{
              backgroundColor: 'var(--s3)', borderColor: 'var(--s3)', color: '#fff',
              display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
              opacity: savingDisabled && !isSaving ? 0.5 : 1,
              transition: 'opacity 200ms',
            }}
          >
            {isSaving ? <Spinner /> : saveSuccess ? 'Saved' : 'Save changes'}
          </button>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {isLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--oc-muted)', fontSize: '0.875rem' }}>
              <Spinner /> Loading title rules
            </div>
          )}
          {error && (
            <div style={{
              border: '1.5px solid var(--oc-fail-bg)',
              background: 'var(--oc-fail-bg)',
              color: 'var(--oc-fail-text)',
              borderRadius: '0.5rem',
              padding: '0.75rem 0.875rem',
              fontSize: '0.8125rem',
            }}>
              {error}
            </div>
          )}

          <RuleChipEditor
            label="Include titles"
            tone="include"
            rules={includeRules}
            draft={includeDraft}
            placeholder="Add target title"
            disabled={isLoading || isSaving}
            onDraftChange={(value) => { setIncludeDraft(value); setSaveSuccess(false); setError('') }}
            onRulesChange={setIncludeRules}
            onDirty={markDirty}
          />

          <RuleChipEditor
            label="Exclude titles"
            tone="exclude"
            rules={excludeRules}
            draft={excludeDraft}
            placeholder="Add excluded title"
            disabled={isLoading || isSaving}
            onDraftChange={(value) => { setExcludeDraft(value); setSaveSuccess(false); setError('') }}
            onRulesChange={setExcludeRules}
            onDirty={markDirty}
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
        onConfirm={() => {
          setShowUnsaved(false)
          setIsDirty(false)
          setIncludeDraft('')
          setExcludeDraft('')
          onClose()
        }}
      >
        You have unsaved changes. They will be lost if you close without saving.
      </ConfirmDialog>
    </>
  )
}
