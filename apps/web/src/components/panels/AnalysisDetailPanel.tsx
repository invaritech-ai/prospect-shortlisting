import type { AnalysisJobDetailRead, AnalysisRunJobRead, RunRead } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Skeleton } from '../ui/Skeleton'
import { IconArrowLeft, IconEye } from '../ui/icons'

// ── Badge helpers ──────────────────────────────────────────────────────────

function decisionBadgeVariant(label: string | null): 'success' | 'neutral' | 'fail' {
  if (!label) return 'neutral'
  const n = label.toLowerCase()
  if (n === 'possible') return 'success'
  if (n === 'unknown') return 'neutral'
  return 'fail'
}

function stateBadge(state: string, terminal: boolean): { variant: 'info' | 'success' | 'fail' | 'neutral'; label: string } {
  const n = state.toLowerCase()
  if (!terminal && (n === 'running' || n === 'queued')) {
    return { variant: 'info', label: n === 'queued' ? 'Queued' : 'Running' }
  }
  if (n === 'failed' || n === 'dead') return { variant: 'fail', label: 'Failed' }
  if (n === 'succeeded') return { variant: 'success', label: 'Done' }
  return { variant: 'neutral', label: state }
}

function runBadge(run: RunRead): { variant: 'info' | 'success' | 'fail'; label: string } {
  if (run.status === 'running' || run.status === 'created') return { variant: 'info', label: 'Running' }
  if (run.status === 'failed') return { variant: 'fail', label: 'Failed' }
  return { variant: 'success', label: 'Done' }
}

// ── Run jobs list ──────────────────────────────────────────────────────────

function RunJobsTable({
  inspectedRun,
  runJobs,
  isLoading,
  error,
  onInspectJob,
}: {
  inspectedRun: RunRead
  runJobs: AnalysisRunJobRead[]
  isLoading: boolean
  error: string
  onInspectJob: (job: AnalysisRunJobRead) => void
}) {
  return (
    <div className="space-y-4 p-5">
      {/* Run summary */}
      <div className="grid gap-3 rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4 sm:grid-cols-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Prompt</p>
          <p className="mt-1.5 text-sm font-semibold text-[var(--oc-accent-ink)]">{inspectedRun.prompt_name}</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Progress</p>
          <p className="mt-1.5 text-sm font-semibold text-[var(--oc-accent-ink)]">
            {inspectedRun.completed_jobs + inspectedRun.failed_jobs}/{inspectedRun.total_jobs}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Failures</p>
          <p className="mt-1.5 text-sm font-semibold text-[var(--oc-accent-ink)]">{inspectedRun.failed_jobs}</p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-xl" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
          <p className="text-sm text-[var(--oc-muted)]">{error}</p>
        </div>
      ) : runJobs.length === 0 ? (
        <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
          <p className="text-sm text-[var(--oc-muted)]">No jobs found for this run.</p>
        </div>
      ) : (
        <>
          {/* Mobile cards */}
          <div className="space-y-2 md:hidden">
            {runJobs.map((job) => {
              const badge = stateBadge(job.state, job.terminal_state)
              return (
                <div key={job.analysis_job_id} className="rounded-xl border border-[var(--oc-border)] bg-white p-3">
                  <div className="flex items-center justify-between gap-2">
                    <a
                      href={`https://${job.domain}`}
                      target="_blank"
                      rel="noreferrer"
                      className="truncate font-semibold text-[var(--oc-accent-ink)] hover:underline"
                    >
                      {job.domain}
                    </a>
                    <Button variant="secondary" size="xs" onClick={() => onInspectJob(job)}>
                      <IconEye size={13} /> Detail
                    </Button>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <Badge variant={decisionBadgeVariant(job.predicted_label)}>
                      {job.predicted_label ?? 'No result'}
                    </Badge>
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                    {job.confidence !== null && (
                      <span className="text-[11px] text-[var(--oc-muted)]">
                        conf {job.confidence.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto rounded-2xl border border-[var(--oc-border)] bg-white">
            <table className="oc-compact-table min-w-[660px]">
              <thead>
                <tr>
                  <th>Domain</th>
                  <th>Result</th>
                  <th>State</th>
                  <th>Confidence</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {runJobs.map((job) => {
                  const badge = stateBadge(job.state, job.terminal_state)
                  return (
                    <tr key={job.analysis_job_id}>
                      <td>
                        <a
                          href={`https://${job.domain}`}
                          target="_blank"
                          rel="noreferrer"
                          className="block max-w-[240px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)] hover:underline"
                        >
                          {job.domain}
                        </a>
                      </td>
                      <td>
                        <Badge variant={decisionBadgeVariant(job.predicted_label)}>
                          {job.predicted_label ?? 'No result'}
                        </Badge>
                      </td>
                      <td>
                        <Badge variant={badge.variant}>{badge.label}</Badge>
                      </td>
                      <td className="font-mono text-[12px] text-[var(--oc-muted)]">
                        {job.confidence !== null ? job.confidence.toFixed(2) : '—'}
                      </td>
                      <td>
                        <Button variant="secondary" size="xs" onClick={() => onInspectJob(job)}>
                          <IconEye size={13} /> Inspect
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ── Analysis job detail ────────────────────────────────────────────────────

function AnalysisDetail({ detail }: { detail: AnalysisJobDetailRead }) {
  const evidencePayload = detail.evidence_json ?? null
  const reasoningPayload = detail.reasoning_json ?? null

  const evidenceItems: string[] =
    evidencePayload && Array.isArray(evidencePayload['evidence'])
      ? (evidencePayload['evidence'] as unknown[]).map((item) => String(item))
      : []

  const signals: Record<string, unknown> =
    reasoningPayload &&
    typeof reasoningPayload['signals'] === 'object' &&
    reasoningPayload['signals']
      ? (reasoningPayload['signals'] as Record<string, unknown>)
      : {}

  const otherFields: Record<string, unknown> =
    reasoningPayload &&
    typeof reasoningPayload['other_fields'] === 'object' &&
    reasoningPayload['other_fields']
      ? (reasoningPayload['other_fields'] as Record<string, unknown>)
      : {}

  const rawOutput: string =
    reasoningPayload && typeof reasoningPayload['raw_response'] === 'string'
      ? String(reasoningPayload['raw_response'])
      : ''

  const stateBadgeInfo = stateBadge(detail.state, detail.terminal_state)

  return (
    <div className="space-y-4 p-5">
      {/* Status card */}
      <section className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={decisionBadgeVariant(detail.predicted_label)}>
            {detail.predicted_label ?? 'No result'}
          </Badge>
          <Badge variant={stateBadgeInfo.variant}>{stateBadgeInfo.label}</Badge>
          {detail.confidence !== null && (
            <span className="text-xs text-[var(--oc-muted)]">
              Confidence {detail.confidence.toFixed(2)}
            </span>
          )}
          <a
            href={`https://${detail.domain}`}
            target="_blank"
            rel="noreferrer"
            className="ml-auto text-xs text-[var(--oc-accent-ink)] hover:underline"
          >
            {detail.domain} ↗
          </a>
        </div>
        <p className="mt-2 text-[11px] text-[var(--oc-muted)]">Prompt: {detail.prompt_name}</p>
        {detail.last_error_code && (
          <p className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
            {detail.last_error_code}: {detail.last_error_message || 'No detail'}
          </p>
        )}
      </section>

      {/* Evidence */}
      <section className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
        <p className="mb-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
          Evidence
        </p>
        {evidenceItems.length > 0 ? (
          <div className="space-y-2">
            {evidenceItems.map((item, i) => (
              <blockquote
                key={`${i}:${item.slice(0, 20)}`}
                className="rounded-r-xl border-l-4 border-[var(--oc-accent)] bg-[var(--oc-accent-soft)]/35 px-4 py-3 text-sm leading-7 text-[var(--oc-text)]"
              >
                {item}
              </blockquote>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--oc-muted)]">No evidence captured.</p>
        )}
      </section>

      {/* Signals */}
      {Object.keys(signals).length > 0 && (
        <section className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
            Signals
          </p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(signals).map(([key, value]) => (
              <span
                key={key}
                className="rounded-full border border-[var(--oc-border)] bg-[var(--oc-surface)] px-3 py-1 text-xs font-semibold text-[var(--oc-text)]"
              >
                {key}: {typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Other fields */}
      {Object.keys(otherFields).length > 0 && (
        <section className="rounded-2xl border border-[var(--oc-border)] bg-white p-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
            Other Fields
          </p>
          <div className="space-y-3">
            {Object.entries(otherFields).map(([key, value]) => (
              <div key={key} className="border-b border-[var(--oc-border)] pb-3 last:border-b-0 last:pb-0">
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--oc-muted)]">{key}</p>
                <p className="mt-1 text-sm leading-6 text-[var(--oc-text)]">{String(value)}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Raw output */}
      <details className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
        <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
          Raw Model Output
        </summary>
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-xl bg-white p-4 text-[11px] leading-6 text-[var(--oc-text)]">
          {rawOutput || 'No raw model output stored.'}
        </pre>
      </details>
    </div>
  )
}

// ── Main panel ─────────────────────────────────────────────────────────────

interface AnalysisDetailPanelProps {
  inspectedRun: RunRead | null
  runJobs: AnalysisRunJobRead[]
  isRunJobsLoading: boolean
  runJobsError: string
  analysisDetail: AnalysisJobDetailRead | null
  isAnalysisDetailLoading: boolean
  analysisDetailError: string
  onClose: () => void
  onInspectJob: (job: AnalysisRunJobRead) => void
  onBackFromDetail: () => void
}

export function AnalysisDetailPanel({
  inspectedRun,
  runJobs,
  isRunJobsLoading,
  runJobsError,
  analysisDetail,
  isAnalysisDetailLoading,
  analysisDetailError,
  onClose,
  onInspectJob,
  onBackFromDetail,
}: AnalysisDetailPanelProps) {
  if (!inspectedRun) return null

  const badge = runBadge(inspectedRun)

  const headerActions = analysisDetail ? (
    <Button variant="secondary" size="xs" onClick={onBackFromDetail}>
      <IconArrowLeft size={14} />
      Back
    </Button>
  ) : undefined

  const headerMeta = (
    <div className="flex flex-wrap items-center gap-2">
      {analysisDetail ? (
        <>
          <Badge variant={decisionBadgeVariant(analysisDetail.predicted_label)}>
            {analysisDetail.predicted_label ?? 'No result'}
          </Badge>
          <Badge variant={stateBadge(analysisDetail.state, analysisDetail.terminal_state).variant}>
            {stateBadge(analysisDetail.state, analysisDetail.terminal_state).label}
          </Badge>
          <span className="text-xs text-[var(--oc-muted)]">
            Confidence {analysisDetail.confidence !== null ? analysisDetail.confidence.toFixed(2) : '—'}
          </span>
        </>
      ) : (
        <>
          <Badge variant={badge.variant}>{badge.label}</Badge>
          <span className="text-xs text-[var(--oc-muted)]">
            {inspectedRun.completed_jobs + inspectedRun.failed_jobs}/{inspectedRun.total_jobs}
          </span>
          <span className="text-xs text-[var(--oc-muted)]">
            {parseUTC(inspectedRun.created_at).toLocaleString()}
          </span>
        </>
      )}
    </div>
  )

  return (
    <Drawer
      isOpen={!!inspectedRun}
      onClose={onClose}
      title={analysisDetail ? analysisDetail.domain : inspectedRun.prompt_name}
      subtitle={analysisDetail ? 'Classification Evidence' : 'Run Inspection'}
      size="lg"
      headerMeta={headerMeta}
      headerActions={headerActions}
    >
      {isAnalysisDetailLoading ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-40 w-full rounded-2xl" />
        </div>
      ) : analysisDetailError ? (
        <div className="p-5">
          <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
            <p className="text-sm text-[var(--oc-muted)]">{analysisDetailError}</p>
          </div>
        </div>
      ) : analysisDetail ? (
        <AnalysisDetail detail={analysisDetail} />
      ) : (
        <RunJobsTable
          inspectedRun={inspectedRun}
          runJobs={runJobs}
          isLoading={isRunJobsLoading}
          error={runJobsError}
          onInspectJob={onInspectJob}
        />
      )}
    </Drawer>
  )
}
