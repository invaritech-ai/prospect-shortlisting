import type { PromptRead } from '../../lib/types'
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
  promptEnabled: boolean
  isPromptsLoading: boolean
  isPromptSaving: boolean
  promptError: string
  onSelectPrompt: (prompt: PromptRead) => void
  onNewPrompt: () => void
  onTogglePromptEnabled: (prompt: PromptRead) => void
  onSaveAsNew: () => void
  onUpdateCurrent: () => void
  onSetPromptName: (v: string) => void
  onSetPromptText: (v: string) => void
  onSetPromptEnabled: (v: boolean) => void
  onRefresh: () => void
}

function PromptListItem({
  prompt,
  isEditing,
  isSelected,
  isSaving,
  onSelect,
  onToggleEnabled,
}: {
  prompt: PromptRead
  isEditing: boolean
  isSelected: boolean
  isSaving: boolean
  onSelect: () => void
  onToggleEnabled: () => void
}) {
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
              {new Date(prompt.created_at).toLocaleString()}
            </p>
          </div>
          {isSelected && <Badge variant="info">Active</Badge>}
        </div>
      </button>
      <div className="mt-3 flex items-center justify-between gap-2">
        <Badge variant={prompt.enabled ? 'success' : 'fail'}>
          {prompt.enabled ? 'Enabled' : 'Disabled'}
        </Badge>
        <button
          type="button"
          onClick={onToggleEnabled}
          disabled={isSaving}
          className="rounded-lg border border-[var(--oc-border)] bg-white px-2.5 py-1 text-[11px] font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {prompt.enabled ? 'Disable' : 'Enable'}
        </button>
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
  promptEnabled,
  isPromptsLoading,
  isPromptSaving,
  promptError,
  onSelectPrompt,
  onNewPrompt,
  onTogglePromptEnabled,
  onSaveAsNew,
  onUpdateCurrent,
  onSetPromptName,
  onSetPromptText,
  onSetPromptEnabled,
  onRefresh,
}: PromptLibraryPanelProps) {
  const headerActions = (
    <Button variant="secondary" size="xs" onClick={onRefresh} loading={isPromptsLoading}>
      <IconRefresh size={14} />
    </Button>
  )

  const selectedPrompt = prompts.find((p) => p.id === selectedPromptId) ?? null
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
                  onSelect={() => onSelectPrompt(prompt)}
                  onToggleEnabled={() => onTogglePromptEnabled(prompt)}
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
            <Button variant="ghost" size="md" onClick={onNewPrompt}>
              New blank
            </Button>
          </div>
        </section>
      </div>
    </Drawer>
  )
}
