import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ScrapeJobRead, ScrapePageContentRead } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Skeleton } from '../ui/Skeleton'
import { IconCopy, IconCheck } from '../ui/icons'

const PAGE_KIND_LABELS: Record<string, string> = { home: 'Home', about: 'About', products: 'Products' }

function badgeForJob(job: ScrapeJobRead): { variant: 'info' | 'success' | 'fail'; label: string } {
  if (!job.terminal_state) return { variant: 'info', label: 'Running' }
  if (job.status === 'failed') {
    return { variant: 'fail', label: 'Failed' }
  }
  return { variant: 'success', label: 'Done' }
}

interface MarkdownPreviewPanelProps {
  markdownJob: ScrapeJobRead | null
  markdownPages: ScrapePageContentRead[]
  activeMarkdownPageKind: string
  isMarkdownLoading: boolean
  markdownError: string
  markdownCopyState: string
  onClose: () => void
  onSetActivePageKind: (kind: string) => void
  onCopyMarkdown: (content: string) => void
}

export function MarkdownPreviewPanel({
  markdownJob,
  markdownPages,
  activeMarkdownPageKind,
  isMarkdownLoading,
  markdownError,
  markdownCopyState,
  onClose,
  onSetActivePageKind,
  onCopyMarkdown,
}: MarkdownPreviewPanelProps) {
  if (!markdownJob) return null

  const jobBadge = badgeForJob(markdownJob)
  const activePage = markdownPages.find((p) => p.page_kind === activeMarkdownPageKind) ?? null

  const headerMeta = (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={jobBadge.variant}>{jobBadge.label}</Badge>
        <span className="text-xs text-[var(--oc-muted)]">
          {parseUTC(markdownJob.updated_at).toLocaleString()}
        </span>
      </div>
      {!isMarkdownLoading && markdownPages.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {markdownPages.map((page) => (
            <button
              key={page.id}
              type="button"
              onClick={() => onSetActivePageKind(page.page_kind)}
              className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                activeMarkdownPageKind === page.page_kind
                  ? 'bg-[var(--oc-accent)] text-white'
                  : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
              }`}
            >
              {PAGE_KIND_LABELS[page.page_kind] ?? page.page_kind}
            </button>
          ))}
          {activePage && (
            <Button
              variant="secondary"
              size="xs"
              className="ml-auto"
              onClick={() => onCopyMarkdown(activePage.markdown_content)}
            >
              {markdownCopyState === 'Copied' ? (
                <IconCheck size={13} className="text-emerald-600" />
              ) : (
                <IconCopy size={13} />
              )}
              {markdownCopyState || 'Copy'}
            </Button>
          )}
        </div>
      )}
    </div>
  )

  return (
    <Drawer
      isOpen={!!markdownJob}
      onClose={onClose}
      title={markdownJob.domain}
      subtitle="Markdown Review"
      size="lg"
      headerMeta={headerMeta}
    >
      <div className="p-5">
        {isMarkdownLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        ) : markdownError ? (
          <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
            <p className="text-sm text-[var(--oc-muted)]">{markdownError}</p>
          </div>
        ) : activePage ? (
          <div className="space-y-3">
            <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] px-4 py-2.5">
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                {PAGE_KIND_LABELS[activePage.page_kind] ?? activePage.page_kind}
              </p>
              <p className="mt-1 truncate text-xs font-semibold text-[var(--oc-accent-ink)]" title={activePage.url}>
                {activePage.url}
              </p>
            </div>
            <article className="oc-markdown rounded-2xl border border-[var(--oc-border)] bg-white p-5">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {activePage.markdown_content}
              </ReactMarkdown>
            </article>
          </div>
        ) : (
          <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
            <p className="text-sm text-[var(--oc-muted)]">No markdown content available for this page.</p>
          </div>
        )}
      </div>
    </Drawer>
  )
}
