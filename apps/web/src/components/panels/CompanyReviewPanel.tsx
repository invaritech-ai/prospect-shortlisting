import { useState } from 'react'
import type { CompanyListItem, AnalysisJobDetailRead } from '../../lib/types'
import { Drawer } from '../ui/Drawer'
import { Button } from '../ui/Button'
import { Skeleton } from '../ui/Skeleton'
import { IconThumbUp, IconThumbDown, IconExternalLink } from '../ui/icons'
import { decisionBgClass } from '../ui/badgeUtils'

interface CompanyReviewPanelProps {
  company: CompanyListItem | null
  detail: AnalysisJobDetailRead | null
  isLoading: boolean
  error: string
  isSaving: boolean
  onClose: () => void
  onSave: (thumbs: 'up' | 'down' | null, comment: string) => void
}

// ── Helpers ────────────────────────────────────────────────────────────────

/** Coerce an evidence item (string, dict, or unknown) to display text */
function evidenceToString(item: unknown): string {
  if (typeof item === 'string') return item
  if (item && typeof item === 'object') {
    const obj = item as Record<string, unknown>
    // Common field names the LLM might use
    for (const key of ['text', 'quote', 'excerpt', 'content', 'value']) {
      if (typeof obj[key] === 'string') return obj[key] as string
    }
    return JSON.stringify(item)
  }
  return String(item)
}

/** Extract evidence array from evidence_json (handles various LLM shapes) */
function extractEvidence(evidence_json: Record<string, unknown> | null | undefined): string[] {
  if (!evidence_json) return []
  const raw = evidence_json['evidence']
  if (Array.isArray(raw)) return raw.map(evidenceToString).filter(Boolean)
  if (typeof raw === 'string' && raw.trim()) return [raw]
  return []
}

/** Extract signals dict from reasoning_json */
function extractSignals(reasoning_json: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!reasoning_json) return {}
  const raw = reasoning_json['signals']
  if (!raw) return {}
  if (Array.isArray(raw)) {
    // Array of signal objects → flatten into a dict
    const out: Record<string, unknown> = {}
    raw.forEach((item, i) => {
      if (item && typeof item === 'object') {
        const obj = item as Record<string, unknown>
        const name = (obj['name'] ?? obj['label'] ?? obj['key'] ?? `signal_${i}`) as string
        out[name] = obj['value'] ?? obj['result'] ?? true
      } else {
        out[`signal_${i}`] = item
      }
    })
    return out
  }
  if (typeof raw === 'object') return raw as Record<string, unknown>
  return {}
}

// ── Sub-components ─────────────────────────────────────────────────────────

function SignalChip({ label, value }: { label: string; value: unknown }) {
  const display = typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)
  const positive = value === true || (typeof value === 'string' && ['yes', 'true', 'high'].includes(value.toLowerCase()))
  const negative = value === false || (typeof value === 'string' && ['no', 'false', 'low', 'none'].includes(value.toLowerCase()))
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
        positive
          ? 'bg-emerald-50 text-emerald-700'
          : negative
          ? 'bg-rose-50 text-rose-700'
          : 'bg-slate-100 text-slate-600'
      }`}
    >
      <span className="opacity-60">{label.replace(/_/g, ' ')}:</span>
      {display}
    </span>
  )
}

const JOB_STATE_LABEL: Record<string, string> = {
  queued: 'Queued — waiting to run',
  running: 'Running — classification in progress',
  failed: 'Failed',
  dead: 'Dead — max retries exhausted',
  succeeded: 'Succeeded',
}

// ── Panel ──────────────────────────────────────────────────────────────────

export function CompanyReviewPanel({
  company,
  detail,
  isLoading,
  error,
  isSaving,
  onClose,
  onSave,
}: CompanyReviewPanelProps) {
  const [draftByCompany, setDraftByCompany] = useState<Record<string, { thumbs: 'up' | 'down' | null; comment: string }>>({})

  if (!company) return null

  const draft = draftByCompany[company.id] ?? {
    thumbs: company.feedback_thumbs ?? null,
    comment: company.feedback_comment ?? '',
  }
  const thumbs = draft.thumbs
  const comment = draft.comment
  const setThumbs = (next: 'up' | 'down' | null) => {
    setDraftByCompany((current) => ({
      ...current,
      [company.id]: {
        ...(current[company.id] ?? { thumbs: company.feedback_thumbs ?? null, comment: company.feedback_comment ?? '' }),
        thumbs: next,
      },
    }))
  }
  const setComment = (next: string) => {
    setDraftByCompany((current) => ({
      ...current,
      [company.id]: {
        ...(current[company.id] ?? { thumbs: company.feedback_thumbs ?? null, comment: company.feedback_comment ?? '' }),
        comment: next,
      },
    }))
  }

  const hasClassification = !!detail?.predicted_label
  const evidenceItems = extractEvidence(detail?.evidence_json ?? null)
  const signals = extractSignals(detail?.reasoning_json ?? null)
  const rawResponse = detail?.reasoning_json?.['raw_response']

  const headerMeta = (
    <div className="flex flex-wrap items-center gap-2">
      <a
        href={`https://${company.domain}`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1 text-xs font-semibold text-(--oc-accent-ink) hover:underline"
      >
        {company.domain}
        <IconExternalLink size={12} className="opacity-60" />
      </a>
      {company.latest_decision && (
        <span className={`oc-badge ${decisionBgClass(company.latest_decision)}`}>
          {company.latest_decision}
          {detail?.confidence != null && (
            <span className="ml-1 opacity-70">· {(detail.confidence * 100).toFixed(0)}%</span>
          )}
        </span>
      )}
      {detail?.prompt_name && (
        <span className="text-[10px] text-(--oc-muted)">via {detail.prompt_name}</span>
      )}
    </div>
  )

  return (
    <Drawer
      isOpen={!!company}
      onClose={onClose}
      title={company.domain}
      subtitle="AI Review & Feedback"
      size="lg"
      headerMeta={headerMeta}
    >
      <div className="p-5 space-y-6">

        {/* Analysis section */}
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-4 w-3/5" />
          </div>

        ) : error ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
            <p className="text-sm font-semibold text-rose-700">Failed to load analysis</p>
            <p className="mt-1 text-xs text-rose-600">{error}</p>
          </div>

        ) : !company.latest_analysis_job_id ? (
          <div className="rounded-2xl border border-dashed border-(--oc-border) bg-(--oc-surface) p-6 text-center">
            <p className="text-sm font-semibold text-(--oc-accent-ink)">No AI analysis yet</p>
            <p className="mt-1 text-xs text-(--oc-muted)">Run classification to see reasoning here.</p>
          </div>

        ) : detail ? (
          <>
            {/* Job state banner when no classification result */}
            {!hasClassification && (
              <div className={`rounded-2xl border p-4 ${
                detail.state === 'failed' || detail.state === 'dead'
                  ? 'border-rose-200 bg-rose-50'
                  : 'border-amber-200 bg-amber-50'
              }`}>
                <p className={`text-sm font-semibold ${
                  detail.state === 'failed' || detail.state === 'dead' ? 'text-rose-700' : 'text-amber-700'
                }`}>
                  {JOB_STATE_LABEL[detail.state] ?? detail.state}
                </p>
                {detail.last_error_message && (
                  <p className="mt-1 text-xs text-rose-600">{detail.last_error_message}</p>
                )}
                {(detail.state === 'queued' || detail.state === 'running') && (
                  <p className="mt-1 text-xs text-amber-600">Results will appear here once classification completes.</p>
                )}
              </div>
            )}

            {/* Evidence */}
            {evidenceItems.length > 0 && (
              <section>
                <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-(--oc-muted)">Evidence</p>
                <div className="space-y-2">
                  {evidenceItems.map((ev, i) => (
                    <blockquote
                      key={i}
                      className="border-l-2 border-(--oc-accent) bg-(--oc-surface) px-4 py-2 text-xs text-(--oc-text) italic rounded-r-lg"
                    >
                      {ev}
                    </blockquote>
                  ))}
                </div>
              </section>
            )}

            {/* Signals */}
            {Object.keys(signals).length > 0 && (
              <section>
                <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-(--oc-muted)">Signals</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(signals).map(([key, val]) => (
                    <SignalChip key={key} label={key} value={val} />
                  ))}
                </div>
              </section>
            )}

            {/* Succeeded but LLM returned no structured content */}
            {hasClassification && evidenceItems.length === 0 && Object.keys(signals).length === 0 && !rawResponse && (
              <div className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
                <p className="text-xs text-(--oc-muted)">
                  Classification completed — no structured evidence or signals were extracted.
                </p>
              </div>
            )}

            {/* Raw output (collapsed) */}
            {rawResponse && (
              <details className="group">
                <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-[0.18em] text-(--oc-muted) hover:text-(--oc-text) list-none flex items-center gap-1.5">
                  <span className="transition-transform group-open:rotate-90">▶</span>
                  Raw model output
                </summary>
                <pre className="mt-2 overflow-x-auto rounded-xl border border-(--oc-border) bg-(--oc-surface) p-3 text-[11px] text-(--oc-muted) whitespace-pre-wrap wrap-break-word">
                  {String(rawResponse)}
                </pre>
              </details>
            )}
          </>

        ) : null}

        {/* Feedback section — always shown */}
        <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4 space-y-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-(--oc-muted)">Your Feedback</p>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setThumbs(thumbs === 'up' ? null : 'up')}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                thumbs === 'up'
                  ? 'border-emerald-500 bg-emerald-50 text-emerald-700'
                  : 'border-(--oc-border) bg-white text-(--oc-muted) hover:border-emerald-400 hover:text-emerald-600'
              }`}
            >
              <IconThumbUp size={14} />
              Good lead
            </button>
            <button
              type="button"
              onClick={() => setThumbs(thumbs === 'down' ? null : 'down')}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-bold transition ${
                thumbs === 'down'
                  ? 'border-rose-400 bg-rose-50 text-rose-700'
                  : 'border-(--oc-border) bg-white text-(--oc-muted) hover:border-rose-400 hover:text-rose-600'
              }`}
            >
              <IconThumbDown size={14} />
              Not relevant
            </button>
            {thumbs !== null && (
              <button
                type="button"
                onClick={() => setThumbs(null)}
                className="text-xs text-(--oc-muted) hover:text-(--oc-text) transition"
              >
                Clear
              </button>
            )}
          </div>

          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a note about this company… (optional)"
            rows={3}
            className="w-full resize-none rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-xs text-(--oc-text) placeholder:text-(--oc-muted) focus:border-(--oc-accent) focus:outline-none focus:ring-1 focus:ring-(--oc-accent)"
          />

          <Button
            variant="primary"
            size="sm"
            onClick={() => onSave(thumbs, comment)}
            loading={isSaving}
            disabled={isSaving}
          >
            Save feedback
          </Button>
        </section>
      </div>
    </Drawer>
  )
}
