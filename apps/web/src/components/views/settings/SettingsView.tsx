import { useEffect, useMemo, useState } from 'react'

import {
  getIntegrationSettings,
  testIntegrationProvider,
  updateIntegrationProvider,
} from '../../../lib/api'
import type {
  IntegrationFieldStatus,
  IntegrationProviderId,
  IntegrationProviderStatus,
  IntegrationsStatusResponse,
  IntegrationTestResponse,
} from '../../../lib/types'
import { parseApiError } from '../../../lib/utils'
import { Badge } from '../../ui/Badge'
import { Button } from '../../ui/Button'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'
import { IconCheck, IconEye, IconRefresh, IconX } from '../../ui/icons'

type ProviderFieldDefinition = {
  field: string
  label: string
  placeholder: string
}

type ProviderDefinition = {
  provider: IntegrationProviderId
  tone: string
  fields: ProviderFieldDefinition[]
}

type ProviderEditorState = {
  values: Record<string, string>
  clears: Record<string, boolean>
  reveals: Record<string, boolean>
  saving: boolean
  testing: boolean
  feedback: IntegrationTestResponse | null
  error: string
  notice: string
}

const PROVIDER_DEFINITIONS: ProviderDefinition[] = [
  {
    provider: 'openrouter',
    tone: 'var(--oc-accent)',
    fields: [
      { field: 'api_key', label: 'API key', placeholder: 'Paste a new OpenRouter API key' },
    ],
  },
  {
    provider: 'snov',
    tone: 'var(--s3)',
    fields: [
      { field: 'client_id', label: 'Client ID', placeholder: 'Paste a new Snov client ID' },
      { field: 'client_secret', label: 'Client secret', placeholder: 'Paste a new Snov client secret' },
    ],
  },
  {
    provider: 'apollo',
    tone: 'var(--s2)',
    fields: [
      { field: 'api_key', label: 'API key', placeholder: 'Paste a new Apollo API key' },
    ],
  },
  {
    provider: 'zerobounce',
    tone: 'var(--s5)',
    fields: [
      { field: 'api_key', label: 'API key', placeholder: 'Paste a new ZeroBounce API key' },
    ],
  },
]

function createEmptyEditorState(): Record<IntegrationProviderId, ProviderEditorState> {
  return {
    openrouter: { values: {}, clears: {}, reveals: {}, saving: false, testing: false, feedback: null, error: '', notice: '' },
    snov: { values: {}, clears: {}, reveals: {}, saving: false, testing: false, feedback: null, error: '', notice: '' },
    apollo: { values: {}, clears: {}, reveals: {}, saving: false, testing: false, feedback: null, error: '', notice: '' },
    zerobounce: { values: {}, clears: {}, reveals: {}, saving: false, testing: false, feedback: null, error: '', notice: '' },
  }
}

function fieldStatusByName(provider: IntegrationProviderStatus | undefined, field: string): IntegrationFieldStatus | undefined {
  return provider?.fields.find((item) => item.field === field)
}

function fieldSourceBadge(fieldStatus: IntegrationFieldStatus | undefined): { variant: 'success' | 'warn' | 'neutral'; label: string } {
  if (!fieldStatus?.is_set) return { variant: 'neutral', label: 'Not set' }
  if (fieldStatus.source === 'db') return { variant: 'success', label: 'DB active' }
  if (fieldStatus.source === 'env') return { variant: 'warn', label: 'Env fallback' }
  return { variant: 'neutral', label: 'Stored' }
}

function providerSummary(provider: IntegrationProviderStatus): string {
  const dbCount = provider.fields.filter((field) => field.source === 'db').length
  const envCount = provider.fields.filter((field) => field.source === 'env').length
  if (dbCount > 0 && envCount > 0) return `${dbCount} DB field(s), ${envCount} env fallback`
  if (dbCount > 0) return `${dbCount} field(s) stored in DB`
  if (envCount > 0) return `${envCount} field(s) using env fallback`
  if (provider.fields.some((field) => field.is_set)) return 'Stored, but runtime source unavailable'
  return 'No credentials set'
}

export function SettingsView() {
  const [status, setStatus] = useState<IntegrationsStatusResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [editors, setEditors] = useState<Record<IntegrationProviderId, ProviderEditorState>>(() => createEmptyEditorState())

  const loadSettings = async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') setIsLoading(true)
    if (mode === 'refresh') setIsRefreshing(true)
    setLoadError('')
    try {
      const response = await getIntegrationSettings()
      setStatus(response)
    } catch (err) {
      setLoadError(parseApiError(err))
    } finally {
      if (mode === 'initial') setIsLoading(false)
      if (mode === 'refresh') setIsRefreshing(false)
    }
  }

  useEffect(() => {
    void loadSettings('initial')
  }, [])

  const providers = useMemo(
    () =>
      PROVIDER_DEFINITIONS.map((definition) => ({
        definition,
        status: status?.providers.find((provider) => provider.provider === definition.provider),
      })),
    [status],
  )

  const setProviderState = (
    provider: IntegrationProviderId,
    updater: (current: ProviderEditorState) => ProviderEditorState,
  ) => {
    setEditors((current) => ({
      ...current,
      [provider]: updater(current[provider]),
    }))
  }

  const replaceProviderStatus = (nextProvider: IntegrationProviderStatus) => {
    setStatus((current) => {
      if (!current) return current
      return {
        ...current,
        providers: current.providers.map((provider) =>
          provider.provider === nextProvider.provider ? nextProvider : provider,
        ),
      }
    })
  }

  const saveProvider = async (
    provider: IntegrationProviderId,
    fields: ProviderFieldDefinition[],
  ) => {
    const editor = editors[provider]
    const payloadFields = fields
      .map((field) => {
        const value = (editor.values[field.field] ?? '').trim()
        const shouldClear = Boolean(editor.clears[field.field])
        if (!value && !shouldClear) return null
        return { field: field.field, value: shouldClear ? '' : value }
      })
      .filter((field): field is { field: string; value: string } => field !== null)

    if (payloadFields.length === 0) return

    setProviderState(provider, (current) => ({
      ...current,
      saving: true,
      error: '',
      notice: '',
    }))

    try {
      const updated = await updateIntegrationProvider(provider, { fields: payloadFields })
      replaceProviderStatus(updated)
      setProviderState(provider, (current) => ({
        ...current,
        saving: false,
        values: {},
        clears: {},
        reveals: {},
        feedback: null,
        error: '',
        notice: 'Securely saved. Runtime will use the DB value first.',
      }))
    } catch (err) {
      setProviderState(provider, (current) => ({
        ...current,
        saving: false,
        error: parseApiError(err),
        notice: '',
      }))
    }
  }

  const runProviderTest = async (provider: IntegrationProviderId) => {
    setProviderState(provider, (current) => ({
      ...current,
      testing: true,
      error: '',
      notice: '',
      feedback: null,
    }))
    try {
      const feedback = await testIntegrationProvider(provider)
      setProviderState(provider, (current) => ({
        ...current,
        testing: false,
        feedback,
        notice: feedback.ok ? 'Connection test passed.' : '',
        error: feedback.ok ? '' : feedback.message,
      }))
    } catch (err) {
      setProviderState(provider, (current) => ({
        ...current,
        testing: false,
        feedback: null,
        notice: '',
        error: parseApiError(err),
      }))
    }
  }

  if (isLoading) {
    return (
      <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
        <p className="text-sm text-(--oc-muted)">Loading integration settings…</p>
      </section>
    )
  }

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-3xl border border-(--oc-border) bg-(--oc-surface)">
        <div className="border-b border-(--oc-border) bg-[linear-gradient(135deg,rgba(20,157,221,0.12),rgba(20,157,221,0.03)_42%,transparent_72%)] px-5 py-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="info">Global control plane</Badge>
                <Badge variant={status?.store_available ? 'success' : 'warn'}>
                  {status?.store_available ? 'Encrypted DB writes enabled' : 'Encrypted DB writes disabled'}
                </Badge>
              </div>
              <div>
                <h2 className="text-lg font-extrabold tracking-tight text-(--oc-accent-ink)">Integration Settings</h2>
                <p className="mt-1 max-w-3xl text-sm text-(--oc-muted)">
                  Database secrets take precedence at runtime. If a DB value is missing, the app falls back to the
                  existing environment variable for that field.
                </p>
              </div>
            </div>
            <Button variant="secondary" size="sm" onClick={() => void loadSettings('refresh')} loading={isRefreshing}>
              <IconRefresh size={15} />
              Refresh
            </Button>
          </div>
        </div>

        <div className="grid gap-3 border-b border-(--oc-border) bg-(--oc-surface) px-5 py-4 md:grid-cols-3">
          <div className="rounded-2xl border border-(--oc-border) bg-white px-4 py-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-(--oc-muted)">Runtime precedence</p>
            <p className="mt-2 text-sm font-semibold text-(--oc-text)">DB first, env second</p>
            <p className="mt-1 text-xs text-(--oc-muted)">Saves are encrypted at rest when the master key is configured.</p>
          </div>
          <div className="rounded-2xl border border-(--oc-border) bg-white px-4 py-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-(--oc-muted)">Operational safety</p>
            <p className="mt-2 text-sm font-semibold text-(--oc-text)">Blank inputs do nothing</p>
            <p className="mt-1 text-xs text-(--oc-muted)">Existing DB secrets and env fallback values stay untouched until you save a real change.</p>
          </div>
          <div className="rounded-2xl border border-(--oc-border) bg-white px-4 py-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-(--oc-muted)">Scope</p>
            <p className="mt-2 text-sm font-semibold text-(--oc-text)">Global providers</p>
            <p className="mt-1 text-xs text-(--oc-muted)">These settings are not campaign-scoped and apply across the whole workspace.</p>
          </div>
        </div>

        {!status?.store_available ? (
          <div className="mx-5 mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            DB-backed secret updates are disabled until `PS_SETTINGS_ENCRYPTION_KEY` is configured on the backend.
            Existing env fallback values can still be used and tested.
          </div>
        ) : null}

        {loadError ? (
          <div className="mx-5 mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {loadError}
          </div>
        ) : null}

        <div className="grid gap-4 p-5 xl:grid-cols-2">
          {providers.map(({ definition, status: providerStatus }) => {
            const editor = editors[definition.provider]
            const hasPendingChanges = definition.fields.some(
              (field) => (editor.values[field.field] ?? '').trim() || editor.clears[field.field],
            )

            return (
              <section
                key={definition.provider}
                className="rounded-3xl border border-(--oc-border) bg-white p-4 shadow-[0_1px_0_rgba(7,21,31,0.03)]"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: definition.tone }}
                        aria-hidden="true"
                      />
                      <h3 className="text-base font-bold tracking-tight text-(--oc-accent-ink)">
                        {providerStatus?.label ?? definition.provider}
                      </h3>
                    </div>
                    <p className="mt-1 text-sm text-(--oc-muted)">
                      {providerStatus?.description ?? 'Provider settings'}
                    </p>
                  </div>
                  <Badge variant="neutral">{providerStatus ? providerSummary(providerStatus) : 'Loading status'}</Badge>
                </div>

                <div className="mt-4 space-y-4">
                  {definition.fields.map((field) => {
                    const statusForField = fieldStatusByName(providerStatus, field.field)
                    const badge = fieldSourceBadge(statusForField)
                    const currentValue = editor.values[field.field] ?? ''
                    const isClearing = Boolean(editor.clears[field.field])
                    const isRevealed = Boolean(editor.reveals[field.field])

                    return (
                      <div key={field.field} className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <label className="text-sm font-semibold text-(--oc-text)" htmlFor={`${definition.provider}-${field.field}`}>
                              {field.label}
                            </label>
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-(--oc-muted)">
                              <Badge variant={badge.variant}>{badge.label}</Badge>
                              {statusForField?.last4 ? (
                                <span>Masked ending: ••••{statusForField.last4}</span>
                              ) : (
                                <span>No stored value visible from this source yet.</span>
                              )}
                              <span>
                                <RelativeTimeLabel timestamp={statusForField?.updated_at} prefix="Updated" />
                              </span>
                            </div>
                          </div>
                          {(statusForField?.source === 'db' || (statusForField?.is_set && statusForField?.source === '')) ? (
                            <Button
                              variant={isClearing ? 'danger' : 'ghost'}
                              size="xs"
                              onClick={() =>
                                setProviderState(definition.provider, (current) => ({
                                  ...current,
                                  clears: {
                                    ...current.clears,
                                    [field.field]: !current.clears[field.field],
                                  },
                                  values: {
                                    ...current.values,
                                    [field.field]: '',
                                  },
                                  notice: '',
                                  error: '',
                                }))
                              }
                            >
                              {isClearing ? (
                                <>
                                  <IconX size={13} />
                                  Cancel clear
                                </>
                              ) : (
                                <>
                                  <IconX size={13} />
                                  Clear stored DB value
                                </>
                              )}
                            </Button>
                          ) : null}
                        </div>

                        <div className="mt-3 flex flex-col gap-2 md:flex-row">
                          <input
                            id={`${definition.provider}-${field.field}`}
                            type={isRevealed ? 'text' : 'password'}
                            value={currentValue}
                            onChange={(event) =>
                              setProviderState(definition.provider, (current) => ({
                                ...current,
                                values: {
                                  ...current.values,
                                  [field.field]: event.target.value,
                                },
                                clears: {
                                  ...current.clears,
                                  [field.field]: false,
                                },
                                notice: '',
                                error: '',
                              }))
                            }
                            placeholder={field.placeholder}
                            className="min-h-11 flex-1 rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-sm outline-none placeholder:text-(--oc-muted) focus:border-(--oc-accent)"
                            aria-describedby={`${definition.provider}-${field.field}-help`}
                          />
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() =>
                              setProviderState(definition.provider, (current) => ({
                                ...current,
                                reveals: {
                                  ...current.reveals,
                                  [field.field]: !current.reveals[field.field],
                                },
                              }))
                            }
                          >
                            <IconEye size={15} />
                            {isRevealed ? 'Hide' : 'Show'}
                          </Button>
                        </div>
                        <p id={`${definition.provider}-${field.field}-help`} className="mt-2 text-xs text-(--oc-muted)">
                          {isClearing
                            ? 'This field will remove the stored DB value and fall back to env if one exists.'
                            : 'Leave blank to keep the current value unchanged.'}
                        </p>
                      </div>
                    )
                  })}
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-(--oc-border) pt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => void saveProvider(definition.provider, definition.fields)}
                      loading={editor.saving}
                      disabled={!hasPendingChanges}
                    >
                      Save changes
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void runProviderTest(definition.provider)}
                      loading={editor.testing}
                    >
                      Test connection
                    </Button>
                  </div>

                  {editor.feedback ? (
                    <Badge variant={editor.feedback.ok ? 'success' : 'fail'}>
                      {editor.feedback.ok ? 'Connection OK' : 'Connection failed'}
                    </Badge>
                  ) : null}
                </div>

                {editor.notice ? (
                  <div className="mt-3 flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                    <IconCheck size={16} className="mt-0.5 shrink-0" />
                    <span>{editor.notice}</span>
                  </div>
                ) : null}

                {editor.error ? (
                  <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                    {editor.error}
                  </div>
                ) : null}

                {editor.feedback && !editor.feedback.ok ? (
                  <p className="mt-2 text-xs text-(--oc-muted)">
                    Tested against the current runtime source: <span className="font-semibold">{editor.feedback.source || 'missing'}</span>
                  </p>
                ) : null}
              </section>
            )
          })}
        </div>
      </section>
    </div>
  )
}
