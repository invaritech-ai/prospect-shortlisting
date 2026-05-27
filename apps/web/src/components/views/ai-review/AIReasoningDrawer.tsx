import { useEffect, useMemo, useState } from 'react'
import type { MockAIRow } from '../../../lib/useAppData'
import type { AiReviewDomainAnalysis } from '../../../lib/types'
import { getAiReviewDomainAnalysis } from '../../../lib/api'
import { Drawer } from '../../ui/Drawer'
import { VerdictBadge } from './VerdictBadge'

interface AIReasoningDrawerProps {
  row: MockAIRow | null
  campaignId: string
  onClose: () => void
}

type EvidenceItem = {
  text: string
  url: string | null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function parseEvidence(value: unknown): EvidenceItem[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => asString(item))
    .filter((item): item is string => Boolean(item))
    .map((item) => {
      const match = item.match(/\s*\((https?:\/\/[^)]+)\)\s*$/i)
      return {
        text: match ? item.slice(0, match.index).trim() : item,
        url: match?.[1] ?? null,
      }
    })
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function valueText(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(valueText).join(', ')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return 'Not found'
}

function toPercent(value: number | null | undefined): number {
  if (value == null) return 0
  return Math.round(value * 100)
}

function toVerdictLabel(value: string | null | undefined): MockAIRow['verdict'] {
  const normalized = (value ?? '').trim().toLowerCase()
  if (!normalized) return 'Unclassified'
  if (normalized === 'possible') return 'Possible'
  if (normalized === 'crap') return 'Crap'
  if (normalized === 'unknown') return 'Unknown'
  return 'Unknown'
}

function buildReasoningSummary(reasoning: Record<string, unknown> | null): string {
  const explicit = asString(reasoning?.summary)
  if (explicit) return explicit

  const otherFields = asRecord(reasoning?.other_fields)
  const products = asString(otherFields?.products_evidence)
  const commerce = asString(otherFields?.commerce_capability)
  const keywords = asString(otherFields?.industry_keywords)
  const parts = [products, commerce, keywords].filter(Boolean)
  if (parts.length > 0) return parts.join(' ')

  return reasoning ? 'Classification completed from the scraped website evidence.' : 'No AI reasoning has been generated yet.'
}

function compactDate(iso: string | null | undefined): string {
  if (!iso) return 'Not reviewed'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  }).format(new Date(iso))
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: '1.5rem' }}>
      <p style={{
        fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.18em',
        color: 'var(--oc-muted)', margin: '0 0 0.625rem',
      }}>
        {title}
      </p>
      {children}
    </section>
  )
}

export function AIReasoningDrawer({ row, campaignId, onClose }: AIReasoningDrawerProps) {
  const [detail, setDetail] = useState<AiReviewDomainAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!row) return
    let cancelled = false
    setDetail(null)
    setError(null)
    setLoading(true)
    getAiReviewDomainAnalysis(campaignId, row.id)
      .then((data) => {
        if (!cancelled) setDetail(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load AI analysis.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [campaignId, row])

  const model = detail ?? null
  const reasoning = useMemo(() => asRecord(model?.reasoning_json), [model])
  const evidenceJson = useMemo(() => asRecord(model?.evidence_json), [model])
  const evidence = useMemo(() => parseEvidence(evidenceJson?.evidence), [evidenceJson])
  const signals = useMemo(() => asRecord(reasoning?.signals), [reasoning])
  const otherFields = useMemo(() => asRecord(reasoning?.other_fields), [reasoning])
  const rawResponse = asString(reasoning?.raw_response)

  if (!row) return null

  const verdict = toVerdictLabel(model?.effective_label ?? row.verdict)
  const confidence = model ? toPercent(model.effective_confidence) : row.confidence
  const confidenceColor = confidence >= 80 ? 'var(--s2)' : confidence >= 50 ? 'var(--oc-warn-text)' : 'var(--oc-fail-text)'
  const priorityScore = typeof reasoning?.priority_score === 'number' ? reasoning.priority_score : null
  const summary = buildReasoningSummary(reasoning)
  const siteUrl = model?.normalized_url || model?.raw_url || row.url
  const hasManualOverride = Boolean(model?.manual_label)

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title={row.domain}
      subtitle="S2 · AI Analysis"
      accentColor="var(--s2)"
      size="lg"
    >
      <div style={{
        display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: '1rem', alignItems: 'center',
        padding: '1.125rem 1.25rem', borderRadius: '1rem', background: 'linear-gradient(135deg, var(--s2-bg), color-mix(in srgb, var(--s2-bg) 62%, white))',
        border: '1.5px solid color-mix(in srgb, var(--s2) 22%, var(--oc-border))', marginBottom: '1rem',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem', minWidth: 0 }}>
          <VerdictBadge verdict={verdict} size="md" />
          <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
            Reviewed {compactDate(model?.activity_at ?? row.updatedAt)}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.125rem', justifyContent: 'flex-end' }}>
          {priorityScore != null && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 900, color: 'var(--oc-text)', lineHeight: 1 }}>{priorityScore}</div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>priority</div>
            </div>
          )}
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '2rem', fontWeight: 900, color: confidenceColor, lineHeight: 1 }}>{confidence}%</div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>confidence</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 900, color: 'var(--oc-text)', lineHeight: 1 }}>{evidence.length || row.pagesReviewed}</div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)' }}>evidence</div>
          </div>
        </div>
      </div>

      {hasManualOverride && (
        <div style={{
          padding: '0.75rem 0.875rem', borderRadius: '0.75rem', marginBottom: '1rem',
          color: 'var(--s2-text)', background: 'var(--s2-bg)', border: '1px solid color-mix(in srgb, var(--s2) 28%, var(--oc-border))',
          fontSize: '0.8125rem', fontWeight: 650,
        }}>
          Manual override: {model?.manual_label}{model?.manual_comment ? ` · ${model.manual_comment}` : ''}
        </div>
      )}

      {loading && (
        <div style={{ padding: '1rem', borderRadius: '0.875rem', border: '1px solid var(--oc-border)', color: 'var(--oc-muted)', marginBottom: '1rem' }}>
          Loading full analysis…
        </div>
      )}

      {error && (
        <div style={{ padding: '1rem', borderRadius: '0.875rem', border: '1px solid var(--oc-fail-text)', color: 'var(--oc-fail-text)', marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      <Section title="Why this decision">
        <p style={{
          fontSize: '0.9375rem', color: 'var(--oc-text)', lineHeight: 1.7, margin: 0,
          padding: '1rem 1.125rem', backgroundColor: 'var(--oc-surface)', borderRadius: '0.875rem', border: '1px solid var(--oc-border)',
        }}>
          {summary}
        </p>
      </Section>

      <Section title="Evidence found">
        {evidence.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
            {evidence.map((item, index) => (
              <div key={`${item.text}-${index}`} style={{
                padding: '0.875rem 1rem', borderRadius: '0.875rem', background: 'var(--oc-surface)',
                border: '1px solid var(--oc-border)', display: 'grid', gap: '0.5rem',
              }}>
                <div style={{ display: 'flex', gap: '0.625rem', alignItems: 'flex-start' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', color: 'var(--s2)', fontWeight: 900, paddingTop: '0.125rem' }}>
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: 1.55, color: 'var(--oc-text)' }}>{item.text}</p>
                </div>
                {item.url && (
                  <a href={item.url} target="_blank" rel="noopener noreferrer" style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--s2)', textDecoration: 'none',
                    overflowWrap: 'anywhere', marginLeft: '1.875rem', fontWeight: 650,
                  }}>
                    {item.url} ↗
                  </a>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: '1rem', color: 'var(--oc-muted)', border: '1px dashed var(--oc-border)', borderRadius: '0.875rem' }}>
            No evidence snippets are attached to this analysis yet.
          </div>
        )}
      </Section>

      {signals && Object.keys(signals).length > 0 && (
        <Section title="Signal matrix">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {Object.entries(signals).map(([key, value]) => {
              const active = value === true
              return (
                <span key={key} style={{
                  display: 'inline-flex', alignItems: 'center', gap: '0.375rem', padding: '0.375rem 0.625rem',
                  borderRadius: '999px', fontSize: '0.75rem', fontWeight: 700,
                  color: active ? 'var(--s2-text)' : 'var(--oc-muted)',
                  background: active ? 'var(--s2-bg)' : 'var(--oc-bg)',
                  border: `1px solid ${active ? 'color-mix(in srgb, var(--s2) 28%, var(--oc-border))' : 'var(--oc-border)'}`,
                }}>
                  <span aria-hidden="true">{active ? '+' : '-'}</span>
                  {humanizeKey(key)}: {valueText(value)}
                </span>
              )
            })}
          </div>
        </Section>
      )}

      {otherFields && Object.keys(otherFields).length > 0 && (
        <Section title="Classification details">
          <div style={{ display: 'grid', gap: '0.625rem' }}>
            {Object.entries(otherFields).map(([key, value]) => (
              <div key={key} style={{
                display: 'grid', gridTemplateColumns: 'minmax(120px, 0.42fr) minmax(0, 1fr)', gap: '0.75rem',
                padding: '0.75rem 0.875rem', border: '1px solid var(--oc-border)', borderRadius: '0.75rem', background: 'var(--oc-surface)',
              }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', fontWeight: 750 }}>{humanizeKey(key)}</span>
                <span style={{ fontSize: '0.8125rem', color: 'var(--oc-text)', lineHeight: 1.55, overflowWrap: 'anywhere' }}>{valueText(value)}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {rawResponse && (
        <Section title="Debug">
          <details style={{ border: '1px solid var(--oc-border)', borderRadius: '0.875rem', background: 'var(--oc-surface)', padding: '0.875rem 1rem' }}>
            <summary style={{ cursor: 'pointer', fontSize: '0.8125rem', fontWeight: 750, color: 'var(--oc-muted)' }}>
              Raw model response
            </summary>
            <pre style={{
              whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: '0.875rem 0 0', fontSize: '0.75rem',
              lineHeight: 1.5, color: 'var(--oc-text)', fontFamily: 'var(--font-mono)',
            }}>
              {rawResponse}
            </pre>
          </details>
        </Section>
      )}

      <div style={{
        padding: '0.875rem 1rem', borderRadius: '0.875rem', border: '1px solid var(--oc-border)', background: 'var(--oc-surface)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem',
      }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 750, color: 'var(--oc-muted)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Company site</span>
        <a href={siteUrl} target="_blank" rel="noopener noreferrer" style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.875rem', color: 'var(--s2)', textDecoration: 'none', fontWeight: 700,
          overflowWrap: 'anywhere', textAlign: 'right',
        }}>
          {row.domain} ↗
        </a>
      </div>
    </Drawer>
  )
}
