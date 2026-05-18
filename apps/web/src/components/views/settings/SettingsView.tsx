import { useEffect, useMemo, useState } from 'react'
import {
  getIntegrationSettings,
  testIntegrationProvider,
  updateIntegrationProvider,
} from '../../../lib/api'
import { MOCK_INTEGRATIONS_STATUS } from '../../../lib/useAppData'
import type {
  IntegrationFieldStatus,
  IntegrationProviderId,
  IntegrationProviderStatus,
  IntegrationsStatusResponse,
  IntegrationTestResponse,
} from '../../../lib/types'
import { parseApiError } from '../../../lib/utils'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'
import { IconCheck, IconEye, IconRefresh, IconX } from '../../ui/icons'

// ── Provider definitions ──────────────────────────────────────────────────────

const PROVIDERS: Array<{
  provider: IntegrationProviderId
  label: string
  stageColor: string
  fields: Array<{ field: string; label: string; placeholder: string }>
}> = [
  {
    provider: 'openrouter',
    label: 'OpenRouter',
    stageColor: 'var(--oc-accent)',
    fields: [{ field: 'api_key', label: 'API key', placeholder: 'Paste a new OpenRouter API key' }],
  },
  {
    provider: 'apollo',
    label: 'Apollo',
    stageColor: 'var(--s3)',
    fields: [{ field: 'api_key', label: 'API key', placeholder: 'Paste a new Apollo API key' }],
  },
  {
    provider: 'snov',
    label: 'Snov.io',
    stageColor: 'var(--s3)',
    fields: [
      { field: 'client_id',     label: 'Client ID',     placeholder: 'Paste a new Snov client ID' },
      { field: 'client_secret', label: 'Client secret', placeholder: 'Paste a new Snov client secret' },
    ],
  },
  {
    provider: 'zerobounce',
    label: 'ZeroBounce',
    stageColor: 'var(--s5)',
    fields: [{ field: 'api_key', label: 'API key', placeholder: 'Paste a new ZeroBounce API key' }],
  },
]

// ── Editor state ──────────────────────────────────────────────────────────────

type EditorState = {
  values: Record<string, string>
  clears: Record<string, boolean>
  reveals: Record<string, boolean>
  saving: boolean
  testing: boolean
  feedback: IntegrationTestResponse | null
  error: string
  notice: string
}

function emptyEditors(): Record<IntegrationProviderId, EditorState> {
  const blank: EditorState = { values: {}, clears: {}, reveals: {}, saving: false, testing: false, feedback: null, error: '', notice: '' }
  return { openrouter: { ...blank }, snov: { ...blank }, apollo: { ...blank }, zerobounce: { ...blank } }
}

function fieldStatus(provider: IntegrationProviderStatus | undefined, field: string): IntegrationFieldStatus | undefined {
  return provider?.fields.find((f) => f.field === field)
}

function sourcePill(fs: IntegrationFieldStatus | undefined) {
  if (!fs?.is_set)          return { color: 'var(--oc-muted)',       bg: 'var(--oc-surface-dim)', label: 'Not set'      }
  if (fs.source === 'db')   return { color: 'var(--oc-success-text)', bg: 'var(--oc-success-bg)', label: 'DB active'    }
  if (fs.source === 'env')  return { color: 'var(--oc-warn-text)',    bg: 'var(--oc-warn-bg)',    label: 'Env fallback' }
  return { color: 'var(--oc-muted)', bg: 'var(--oc-surface-dim)', label: 'Stored' }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function SettingsView() {
  const [status, setStatus]         = useState<IntegrationsStatusResponse | null>(MOCK_INTEGRATIONS_STATUS)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [loadError, setLoadError]   = useState('')
  const [editors, setEditors]       = useState<Record<IntegrationProviderId, EditorState>>(emptyEditors)

  const load = async (_mode: 'initial' | 'refresh' = 'initial') => {
    setIsRefreshing(true)
    setLoadError('')
    try { setStatus(await getIntegrationSettings()) }
    catch { setStatus(MOCK_INTEGRATIONS_STATUS) }
    finally { setIsRefreshing(false) }
  }

  useEffect(() => { void load('initial') }, [])

  const providers = useMemo(() =>
    PROVIDERS.map((def) => ({ def, providerStatus: status?.providers.find((p) => p.provider === def.provider) })),
    [status],
  )

  function patchEditor(provider: IntegrationProviderId, patch: Partial<EditorState>) {
    setEditors((prev) => ({ ...prev, [provider]: { ...prev[provider], ...patch } }))
  }

  async function saveProvider(provider: IntegrationProviderId) {
    const def    = PROVIDERS.find((p) => p.provider === provider)!
    const editor = editors[provider]
    const fields = def.fields
      .map((f) => {
        const value   = (editor.values[f.field] ?? '').trim()
        const clearing = Boolean(editor.clears[f.field])
        if (!value && !clearing) return null
        return { field: f.field, value: clearing ? '' : value }
      })
      .filter((f): f is { field: string; value: string } => f !== null)
    if (!fields.length) return

    patchEditor(provider, { saving: true, error: '', notice: '' })
    try {
      const updated = await updateIntegrationProvider(provider, { fields })
      setStatus((s) => s ? { ...s, providers: s.providers.map((p) => p.provider === provider ? updated : p) } : s)
      patchEditor(provider, { saving: false, values: {}, clears: {}, reveals: {}, feedback: null, notice: 'Saved. Runtime will use the DB value first.' })
    } catch (err) {
      patchEditor(provider, { saving: false, error: parseApiError(err) })
    }
  }

  async function testProvider(provider: IntegrationProviderId) {
    patchEditor(provider, { testing: true, error: '', notice: '', feedback: null })
    try {
      const feedback = await testIntegrationProvider(provider)
      patchEditor(provider, { testing: false, feedback, notice: feedback.ok ? 'Connection test passed.' : '', error: feedback.ok ? '' : feedback.message })
    } catch (err) {
      patchEditor(provider, { testing: false, error: parseApiError(err) })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
        <div>
          <h1 className="oc-heading-page" style={{ margin: 0 }}>Config</h1>
          <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginTop: '0.375rem' }}>
            API credentials for all pipeline integrations. DB secrets take precedence over env variables at runtime.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {status && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.3125rem',
              padding: '0.25rem 0.625rem', borderRadius: '9999px', fontSize: '0.75rem', fontWeight: 600,
              color: status.store_available ? 'var(--oc-success-text)' : 'var(--oc-warn-text)',
              background: status.store_available ? 'var(--oc-success-bg)' : 'var(--oc-warn-bg)',
            }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '9999px', backgroundColor: 'currentColor' }} />
              {status.store_available ? 'Encrypted DB active' : 'DB writes disabled'}
            </span>
          )}
          <button
            type="button"
            onClick={() => void load('refresh')}
            disabled={isRefreshing}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
              padding: '0.375rem 0.875rem', height: '34px', borderRadius: '0.5rem',
              border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
              fontSize: '0.8125rem', fontWeight: 600, color: 'var(--oc-muted)',
              cursor: 'pointer', fontFamily: 'inherit', opacity: isRefreshing ? 0.55 : 1,
            }}
          >
            <IconRefresh size={13} />
            {isRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Alerts */}
      {!status?.store_available && (
        <div style={{ padding: '0.875rem 1rem', borderRadius: '0.75rem', border: '1.5px solid var(--oc-warn-bg)', background: 'var(--oc-warn-bg)', fontSize: '0.875rem', color: 'var(--oc-warn-text)' }}>
          DB-backed secrets are disabled until <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>PS_SETTINGS_ENCRYPTION_KEY</code> is configured on the backend. Env fallback values can still be tested.
        </div>
      )}
      {loadError && (
        <div style={{ padding: '0.875rem 1rem', borderRadius: '0.75rem', border: '1.5px solid var(--oc-fail-bg)', background: 'var(--oc-fail-bg)', fontSize: '0.875rem', color: 'var(--oc-fail-text)' }}>
          {loadError}
        </div>
      )}

      {/* Provider grid */}
      <div style={{ display: 'grid', gap: '1rem', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))' }}>
        {providers.map(({ def, providerStatus }) => {
          const editor = editors[def.provider]
          const hasPending = def.fields.some((f) => (editor.values[f.field] ?? '').trim() || editor.clears[f.field])

          return (
            <div key={def.provider} className="oc-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>

              {/* Provider header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: def.stageColor, flexShrink: 0 }} />
                  <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.125rem', color: 'var(--oc-text)', margin: 0, lineHeight: 1 }}>
                    {def.label}
                  </h2>
                </div>
                {providerStatus && (
                  <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', fontWeight: 500 }}>
                    {providerStatus.description}
                  </span>
                )}
              </div>

              {/* Fields */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {def.fields.map((f) => {
                  const fs         = fieldStatus(providerStatus, f.field)
                  const pill       = sourcePill(fs)
                  const value      = editor.values[f.field] ?? ''
                  const isClearing = Boolean(editor.clears[f.field])
                  const isRevealed = Boolean(editor.reveals[f.field])

                  return (
                    <div key={f.field} style={{ borderRadius: '0.625rem', border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)', padding: '0.875rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                      {/* Field label row */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <label htmlFor={`${def.provider}-${f.field}`} style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--oc-text)' }}>
                            {f.label}
                          </label>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', padding: '0.125rem 0.5rem', borderRadius: '9999px', fontSize: '0.6875rem', fontWeight: 600, color: pill.color, background: pill.bg }}>
                            {pill.label}
                          </span>
                          {fs?.last4 && (
                            <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', fontFamily: 'var(--font-mono)' }}>
                              ••••{fs.last4}
                            </span>
                          )}
                          {fs?.updated_at && (
                            <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>
                              · <RelativeTimeLabel timestamp={fs.updated_at} prefix="Updated" />
                            </span>
                          )}
                        </div>
                        {(fs?.source === 'db' || (fs?.is_set && fs?.source === '')) && (
                          <button
                            type="button"
                            onClick={() => setEditors((prev) => ({
                              ...prev,
                              [def.provider]: {
                                ...prev[def.provider],
                                clears: { ...prev[def.provider].clears, [f.field]: !prev[def.provider].clears[f.field] },
                                values: { ...prev[def.provider].values, [f.field]: '' },
                                notice: '', error: '',
                              },
                            }))}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                              padding: '0.1875rem 0.5rem', borderRadius: '0.375rem',
                              border: `1.5px solid ${isClearing ? 'var(--oc-fail-text)' : 'var(--oc-border)'}`,
                              background: isClearing ? 'var(--oc-fail-bg)' : 'transparent',
                              color: isClearing ? 'var(--oc-fail-text)' : 'var(--oc-muted)',
                              fontSize: '0.6875rem', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                            }}
                          >
                            <IconX size={11} />
                            {isClearing ? 'Cancel clear' : 'Clear DB value'}
                          </button>
                        )}
                      </div>

                      {/* Input row */}
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                          id={`${def.provider}-${f.field}`}
                          type={isRevealed ? 'text' : 'password'}
                          value={value}
                          onChange={(e) => setEditors((prev) => ({
                            ...prev,
                            [def.provider]: {
                              ...prev[def.provider],
                              values: { ...prev[def.provider].values, [f.field]: e.target.value },
                              clears: { ...prev[def.provider].clears, [f.field]: false },
                              notice: '', error: '',
                            },
                          }))}
                          placeholder={f.placeholder}
                          className="oc-input"
                          style={{ flex: 1 }}
                        />
                        <button
                          type="button"
                          onClick={() => setEditors((prev) => ({
                            ...prev,
                            [def.provider]: { ...prev[def.provider], reveals: { ...prev[def.provider].reveals, [f.field]: !prev[def.provider].reveals[f.field] } },
                          }))}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
                            padding: '0 0.875rem', borderRadius: '0.5rem', flexShrink: 0,
                            border: '1.5px solid var(--oc-border)', background: 'var(--oc-surface)',
                            fontSize: '0.8125rem', fontWeight: 600, color: 'var(--oc-muted)',
                            cursor: 'pointer', fontFamily: 'inherit',
                          }}
                        >
                          <IconEye size={14} />
                          {isRevealed ? 'Hide' : 'Show'}
                        </button>
                      </div>

                      {isClearing && (
                        <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--oc-warn-text)' }}>
                          This will remove the stored DB value and fall back to env if one exists.
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', paddingTop: '0.25rem', borderTop: '1px solid var(--oc-border)', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: '0.375rem' }}>
                  <button
                    type="button"
                    onClick={() => void saveProvider(def.provider)}
                    disabled={!hasPending || editor.saving}
                    className="oc-btn oc-btn-primary oc-btn-sm"
                    style={{ opacity: (!hasPending || editor.saving) ? 0.45 : 1 }}
                  >
                    {editor.saving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    type="button"
                    onClick={() => void testProvider(def.provider)}
                    disabled={editor.testing}
                    className="oc-btn oc-btn-secondary oc-btn-sm"
                    style={{ opacity: editor.testing ? 0.55 : 1 }}
                  >
                    {editor.testing ? 'Testing…' : 'Test connection'}
                  </button>
                </div>

                {editor.feedback && (
                  <span style={{
                    fontSize: '0.75rem', fontWeight: 700,
                    color: editor.feedback.ok ? 'var(--oc-success-text)' : 'var(--oc-fail-text)',
                  }}>
                    {editor.feedback.ok ? '✓ Connection OK' : '✗ Connection failed'}
                  </span>
                )}
              </div>

              {/* Feedback messages */}
              {editor.notice && (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', padding: '0.625rem 0.875rem', borderRadius: '0.625rem', border: '1.5px solid var(--oc-success-bg)', background: 'var(--oc-success-bg)', fontSize: '0.8125rem', color: 'var(--oc-success-text)' }}>
                  <span style={{ flexShrink: 0, marginTop: '1px', display: 'flex' }}><IconCheck size={14} /></span>
                  {editor.notice}
                </div>
              )}
              {editor.error && (
                <div style={{ padding: '0.625rem 0.875rem', borderRadius: '0.625rem', border: '1.5px solid var(--oc-fail-bg)', background: 'var(--oc-fail-bg)', fontSize: '0.8125rem', color: 'var(--oc-fail-text)' }}>
                  {editor.error}
                </div>
              )}
              {editor.feedback && !editor.feedback.ok && (
                <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
                  Tested against: <span style={{ fontWeight: 600 }}>{editor.feedback.source || 'missing'}</span>
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
