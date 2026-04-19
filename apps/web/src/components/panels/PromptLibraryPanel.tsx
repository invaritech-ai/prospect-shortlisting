import { useState } from 'react'
import type { PromptRead, ScrapeRules } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Skeleton } from '../ui/Skeleton'
import { IconPlus, IconRefresh } from '../ui/icons'

interface PromptLibraryPanelProps {
  isOpen: boolean
  onClose: () => void
  prompts: PromptRead[]
  selectedPromptId: string
  editingPromptId: string | null
  promptName: string
  promptText: string
  promptScrapeIntentText: string
  promptEnabled: boolean
  isPromptsLoading: boolean
  isPromptSaving: boolean
  isPromptDeleting: boolean
  promptError: string
  onSelectPrompt: (prompt: PromptRead) => void
  onNewPrompt: () => void
  onTogglePromptEnabled: (prompt: PromptRead) => void
  onDeletePrompt: (prompt: PromptRead) => void
  onClonePrompt: (prompt: PromptRead) => void
  onSaveAsNew: () => void
  onUpdateCurrent: () => void
  onSetPromptName: (v: string) => void
  onSetPromptText: (v: string) => void
  onSetPromptScrapeIntentText: (v: string) => void
  onSetPromptEnabled: (v: boolean) => void
  onRefresh: () => void
}

function formatScrapeRulesPreview(rules: ScrapeRules | null | undefined): string {
  if (!rules) return 'No structured scrape rules generated yet.'
  return JSON.stringify(rules, null, 2)
}

function PromptListItem({
  prompt,
  isEditing,
  isSelected,
  isSaving,
  isDeleting,
  onSelect,
  onToggleEnabled,
  onDelete,
}: {
  prompt: PromptRead
  isEditing: boolean
  isSelected: boolean
  isSaving: boolean
  isDeleting: boolean
  onSelect: () => void
  onToggleEnabled: () => void
  onDelete: () => void
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div
      className={`rounded-2xl border p-3 transition ${
        isEditing
          ? 'border-[var(--oc-accent)] bg-[var(--oc-accent-soft)]/40'
          : 'border-[var(--oc-border)] bg-[var(--oc-surface)]'
      }`}
    >
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-[var(--oc-accent-ink)]">{prompt.name}</p>
            <p className="mt-0.5 text-[11px] text-[var(--oc-muted)]">
              {parseUTC(prompt.created_at).toLocaleString()} ·{' '}
              <span className="font-medium">
                {prompt.run_count} run{prompt.run_count !== 1 ? 's' : ''}
              </span>
            </p>
          </div>
          {isSelected && <Badge variant="info">Active</Badge>}
        </div>
      </button>
      <div className="mt-3 flex items-center justify-between gap-2">
        <Badge variant={prompt.enabled ? 'success' : 'fail'}>
          {prompt.enabled ? 'Enabled' : 'Disabled'}
        </Badge>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onToggleEnabled}
            disabled={isSaving || isDeleting}
            className="rounded-lg border border-[var(--oc-border)] bg-white px-2.5 py-1 text-[11px] font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {prompt.enabled ? 'Disable' : 'Enable'}
          </button>
          {confirmDelete ? (
            <>
              <button
                type="button"
                onClick={() => { setConfirmDelete(false); onDelete() }}
                disabled={isDeleting}
                className="rounded-lg border border-rose-300 bg-rose-50 px-2.5 py-1 text-[11px] font-bold text-rose-700 transition hover:bg-rose-100 disabled:opacity-50"
              >
                {isDeleting ? '…' : 'Confirm'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="rounded-lg border border-[var(--oc-border)] bg-white px-2.5 py-1 text-[11px] text-[var(--oc-muted)] transition hover:border-[var(--oc-accent)]"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              disabled={isSaving || isDeleting}
              className="rounded-lg border border-rose-200 px-2.5 py-1 text-[11px] font-bold text-rose-600 transition hover:border-rose-400 hover:bg-rose-50 disabled:opacity-50"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function PromptLibraryPanel({
  isOpen,
  onClose,
  prompts,
  selectedPromptId,
  editingPromptId,
  promptName,
  promptText,
  promptScrapeIntentText,
  promptEnabled,
  isPromptsLoading,
  isPromptSaving,
  isPromptDeleting,
  promptError,
  onSelectPrompt,
  onNewPrompt,
  onTogglePromptEnabled,
  onDeletePrompt,
  onClonePrompt,
  onSaveAsNew,
  onUpdateCurrent,
  onSetPromptName,
  onSetPromptText,
  onSetPromptScrapeIntentText,
  onSetPromptEnabled,
  onRefresh,
}: PromptLibraryPanelProps) {
  const headerActions = (
    <Button variant="secondary" size="xs" onClick={onRefresh} loading={isPromptsLoading}>
      <IconRefresh size={14} />
    </Button>
  )

  const selectedPrompt = prompts.find((p) => p.id === selectedPromptId) ?? null
  const editingPrompt = prompts.find((p) => p.id === editingPromptId) ?? null
  const headerMeta = selectedPrompt ? (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant={selectedPrompt.enabled ? 'success' : 'fail'}>
        {selectedPrompt.enabled ? 'Active for runs' : 'Selected but disabled'}
      </Badge>
    </div>
  ) : (
    <Badge variant="neutral">No prompt selected</Badge>
  )

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title="Prompt Library"
      subtitle="Prompts"
      size="lg"
      headerMeta={headerMeta}
      headerActions={headerActions}
    >
      {/* Two-column layout: list | editor */}
      <div className="flex h-full flex-col xl:flex-row">
        {/* Prompt list */}
        <aside className="flex-shrink-0 border-b border-[var(--oc-border)] p-4 xl:w-[280px] xl:border-b-0 xl:border-r xl:overflow-y-auto">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="text-sm font-bold">Saved prompts</h3>
            <Button variant="secondary" size="xs" onClick={onNewPrompt}>
              <IconPlus size={13} />
              New
            </Button>
          </div>
          {isPromptsLoading && prompts.length === 0 ? (
            <div className="space-y-2">
              <Skeleton className="h-20 w-full rounded-2xl" />
              <Skeleton className="h-20 w-full rounded-2xl" />
              <Skeleton className="h-20 w-full rounded-2xl" />
            </div>
          ) : prompts.length === 0 ? (
            <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
              <p className="text-sm text-[var(--oc-muted)]">No prompts saved yet. Create one on the right.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {prompts.map((prompt) => (
                <PromptListItem
                  key={prompt.id}
                  prompt={prompt}
                  isEditing={editingPromptId === prompt.id}
                  isSelected={selectedPromptId === prompt.id}
                  isSaving={isPromptSaving}
                  isDeleting={isPromptDeleting}
                  onSelect={() => onSelectPrompt(prompt)}
                  onToggleEnabled={() => onTogglePromptEnabled(prompt)}
                  onDelete={() => onDeletePrompt(prompt)}
                />
              ))}
            </div>
          )}
        </aside>

        {/* Editor */}
        <section className="flex-1 overflow-y-auto p-5">
          <div className="flex items-center justify-between gap-3 mb-5">
            <div>
              <h3 className="text-base font-bold tracking-tight">
                {editingPromptId ? 'Edit prompt' : 'New prompt'}
              </h3>
              <p className="mt-0.5 text-xs text-[var(--oc-muted)]">
                Save as new to preserve history. Update only for minor corrections.
              </p>
            </div>
            <span className="oc-kbd">{editingPromptId ? 'editing' : 'new draft'}</span>
          </div>

          <div className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                Name
              </span>
              <input
                type="text"
                value={promptName}
                onChange={(e) => onSetPromptName(e.target.value)}
                className="w-full rounded-xl border border-[var(--oc-border)] bg-white px-4 py-2.5 text-sm text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)] focus:ring-2 focus:ring-[var(--oc-accent)]/10"
                placeholder="Supplier fit rubric v1"
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                Prompt text
              </span>
              <textarea
                value={promptText}
                onChange={(e) => onSetPromptText(e.target.value)}
                rows={16}
                className="min-h-[280px] w-full rounded-2xl border border-[var(--oc-border)] bg-white px-4 py-3 font-mono text-xs leading-6 text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)] focus:ring-2 focus:ring-[var(--oc-accent)]/10 md:min-h-[360px]"
                placeholder="Paste or write the rubric prompt here."
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                S1 pages intent (plain English)
              </span>
              <textarea
                value={promptScrapeIntentText}
                onChange={(e) => onSetPromptScrapeIntentText(e.target.value)}
                rows={5}
                className="w-full rounded-2xl border border-[var(--oc-border)] bg-white px-4 py-3 text-sm leading-6 text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)] focus:ring-2 focus:ring-[var(--oc-accent)]/10"
                placeholder="Example: Find pricing, product catalog, line card, capabilities/services, and contact pages. Prefer official company pages over blog posts."
              />
              <p className="mt-1 text-xs text-[var(--oc-muted)]">
                Saved prompts are converted to structured scrape rules automatically when you click
                &nbsp;<span className="font-semibold">Save as new</span> or
                &nbsp;<span className="font-semibold">Update current</span>.
              </p>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                Derived S1 scrape rules (read-only)
              </span>
              <textarea
                value={formatScrapeRulesPreview(editingPrompt?.scrape_rules_structured)}
                readOnly
                rows={8}
                className="w-full rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] px-4 py-3 font-mono text-xs leading-6 text-[var(--oc-muted)] outline-none"
              />
            </label>

            <label className="flex cursor-pointer items-center gap-2.5">
              <input
                type="checkbox"
                checked={promptEnabled}
                onChange={(e) => onSetPromptEnabled(e.target.checked)}
                className="h-4 w-4 rounded border-[var(--oc-border)] accent-[var(--oc-accent)]"
              />
              <span className="text-sm font-semibold text-[var(--oc-text)]">Enabled</span>
              <span className="text-xs text-[var(--oc-muted)]">(disabled prompts won't be used for new runs)</span>
            </label>
          </div>

          {promptError && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3">
              <p className="text-sm font-medium text-rose-800">{promptError}</p>
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              size="md"
              onClick={onSaveAsNew}
              loading={isPromptSaving}
            >
              Save as new
            </Button>
            <Button
              variant="secondary"
              size="md"
              onClick={onUpdateCurrent}
              disabled={!editingPromptId || isPromptSaving}
            >
              Update current
            </Button>
            <Button
              variant="secondary"
              size="md"
              onClick={() => {
                const editing = prompts.find((p) => p.id === editingPromptId)
                if (editing) onClonePrompt(editing)
              }}
              disabled={!editingPromptId || isPromptSaving}
            >
              Clone
            </Button>
            <Button variant="ghost" size="md" onClick={onNewPrompt}>
              New blank
            </Button>
          </div>
        </section>
      </div>
    </Drawer>
  )
}
