import type { ScrapeJobRead, ScrapePageContentRead } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Skeleton } from '../ui/Skeleton'
import { IconEye } from '../ui/icons'

interface ScrapeDiagnosticsPanelProps {
  job: ScrapeJobRead | null
  pages: ScrapePageContentRead[]
  isLoading: boolean
  error: string
  onClose: () => void
  onOpenMarkdown: (job: ScrapeJobRead) => void
}

function badgeForJob(job: ScrapeJobRead): { variant: 'info' | 'success' | 'fail' | 'neutral'; label: string } {
  if (!job.terminal_state) return { variant: 'info', label: 'Running' }
  if (job.state === 'site_unavailable') return { variant: 'neutral', label: 'Site Down' }
  if (job.state.includes('failed') || !!job.last_error_code) return { variant: 'fail', label: 'Failed' }
  return { variant: 'success', label: 'Done' }
}

export function ScrapeDiagnosticsPanel({
  job,
  pages,
  isLoading,
  error,
  onClose,
  onOpenMarkdown,
}: ScrapeDiagnosticsPanelProps) {
  if (!job) return null

  const badge = badgeForJob(job)

  return (
    <Drawer
      isOpen={!!job}
      onClose={onClose}
      title={job.domain}
      subtitle="Scrape Diagnostics"
      size="lg"
      headerMeta={(
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={badge.variant}>{badge.label}</Badge>
          <span className="text-xs text-[var(--oc-muted)]">
            {parseUTC(job.updated_at).toLocaleString()}
          </span>
          <span className="text-xs text-[var(--oc-muted)]">
            {job.markdown_pages_count}/{job.pages_fetched_count} markdown pages
          </span>
          {job.last_error_code && (
            <span className="rounded-md bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-700">
              {job.last_error_code}
            </span>
          )}
          {job.markdown_pages_count > 0 && (
            <Button variant="secondary" size="xs" className="ml-auto" onClick={() => onOpenMarkdown(job)}>
              <IconEye size={13} />
              Markdown Review
            </Button>
          )}
        </div>
      )}
    >
      <div className="space-y-4 p-5">
        <section className="grid gap-3 rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4 sm:grid-cols-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Status</p>
            <p className="mt-1.5 text-sm font-semibold text-[var(--oc-accent-ink)]">{job.state}</p>
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">Job ID</p>
            <p className="mt-1.5 font-mono text-xs text-[var(--oc-accent-ink)]">{job.id}</p>
          </div>
        </section>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-xl" />
            ))}
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
            <p className="text-sm text-[var(--oc-muted)]">{error}</p>
          </div>
        ) : pages.length === 0 ? (
          <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
            <p className="text-sm text-[var(--oc-muted)]">No page diagnostics available for this job.</p>
          </div>
        ) : (
          <>
            <div className="space-y-2 md:hidden">
              {pages.map((page) => (
                <div key={page.id} className="rounded-xl border border-[var(--oc-border)] bg-white p-3">
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-[var(--oc-muted)]">
                    {page.page_kind}
                  </p>
                  <p className="mt-1 truncate text-sm font-semibold text-[var(--oc-accent-ink)]" title={page.url}>
                    {page.url}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[var(--oc-muted)]">
                    <span>HTTP {page.status_code}</span>
                    <span>MD {page.markdown_content.trim().length.toLocaleString()} chars</span>
                    {page.fetch_error_code && <span className="text-rose-700">{page.fetch_error_code}</span>}
                  </div>
                </div>
              ))}
            </div>

            <div className="hidden md:block overflow-x-auto rounded-2xl border border-[var(--oc-border)] bg-white">
              <table className="oc-compact-table min-w-[900px]">
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>URL</th>
                    <th>HTTP</th>
                    <th>Fetch Error</th>
                    <th>Markdown</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {pages.map((page) => (
                    <tr key={page.id}>
                      <td className="font-semibold text-[var(--oc-accent-ink)]">{page.page_kind}</td>
                      <td>
                        <a
                          href={page.url}
                          target="_blank"
                          rel="noreferrer"
                          className="block max-w-[360px] overflow-hidden text-ellipsis whitespace-nowrap text-[var(--oc-accent-ink)] hover:underline"
                          title={page.url}
                        >
                          {page.url}
                        </a>
                      </td>
                      <td className="font-mono text-[12px] text-[var(--oc-muted)]">{page.status_code}</td>
                      <td className="text-[12px] text-[var(--oc-muted)]">
                        {page.fetch_error_code ?? '—'}
                      </td>
                      <td className="font-mono text-[12px] text-[var(--oc-muted)]">
                        {page.markdown_content.trim().length.toLocaleString()}
                      </td>
                      <td className="text-[12px] text-[var(--oc-muted)]">
                        {parseUTC(page.updated_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Drawer>
  )
}
