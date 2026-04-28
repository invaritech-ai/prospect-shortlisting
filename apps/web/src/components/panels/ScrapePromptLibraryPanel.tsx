import type { ScrapePromptRead, ScrapeRules } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import {
  DeleteConfirmButtonGroup,
  PromptEditorFieldLabel,
  PromptLibraryAsideEmpty,
  PromptLibraryAsideSkeleton,
  PromptLibraryFormError,
  promptListCardClassNames,
} from './promptLibraryShared'
import { IconPlus, IconRefresh } from '../ui/icons'

interface ScrapePromptLibraryPanelProps {
  isOpen: boolean
  onClose: () => void
  prompts: ScrapePromptRead[]
  selectedPromptId: string
  activePromptId: string
  editingPromptId: string | null
  promptName: string
  promptIntentText: string
  promptEnabled: boolean
  isPromptsLoading: boolean
  isPromptSaving: boolean
  isPromptDeleting: boolean
  promptError: string
  onSelectPrompt: (prompt: ScrapePromptRead) => void
  onNewPrompt: () => void
  onTogglePromptEnabled: (prompt: ScrapePromptRead) => void
  onDeletePrompt: (prompt: ScrapePromptRead) => void
  onActivatePrompt: (prompt: ScrapePromptRead) => void
  onSaveAsNew: () => void
  onUpdateCurrent: () => void
  onSetPromptName: (v: string) => void
  onSetPromptIntentText: (v: string) => void
  onSetPromptEnabled: (v: boolean) => void
  onRefresh: () => void
}

function formatScrapeRulesPreview(rules: ScrapeRules | null | undefined): string {
  if (!rules) return 'No structured rules generated yet.'
  return JSON.stringify(rules, null, 2)
}

function ScrapePromptListItem({
  prompt,
  isEditing,
  isSelected,
  isSaving,
  isDeleting,
  activePromptId,
  onSelect,
  onToggleEnabled,
  onDelete,
  onActivate,
}: {
  prompt: ScrapePromptRead
  isEditing: boolean
  isSelected: boolean
  isSaving: boolean
  isDeleting: boolean
  activePromptId: string
  onSelect: () => void
  onToggleEnabled: () => void
  onDelete: () => void
  onActivate: () => void
}) {
  const isSystemDefault = prompt.is_system_default

  return (
    <div className={promptListCardClassNames(isEditing)}>
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-[var(--oc-accent-ink)]">{prompt.name}</p>
            <p className="mt-0.5 text-[11px] text-[var(--oc-muted)]">
              Updated {parseUTC(prompt.updated_at).toLocaleString()}
            </p>
          </div>
          {isSelected && <Badge variant="info">Selected</Badge>}
        </div>
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {prompt.id === activePromptId && <Badge variant="success">Active</Badge>}
        <Badge variant={prompt.enabled ? 'success' : 'fail'}>
          {prompt.enabled ? 'Enabled' : 'Disabled'}
        </Badge>
        {prompt.is_system_default && <Badge variant="neutral">Default</Badge>}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onToggleEnabled}
          disabled={isSaving || isDeleting || isSystemDefault}
          className="rounded-lg border border-[var(--oc-border)] bg-white px-2.5 py-1 text-[11px] font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {prompt.enabled ? 'Disable' : 'Enable'}
        </button>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onActivate}
            disabled={isSaving || isDeleting || !prompt.enabled || prompt.id === activePromptId || isSystemDefault}
            className="rounded-lg border border-[var(--oc-border)] bg-white px-2.5 py-1 text-[11px] font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Activate
          </button>
          {!prompt.is_system_default ? (
            <DeleteConfirmButtonGroup
              disabled={isSaving || isDeleting}
              isDeleting={isDeleting}
              onConfirmDelete={onDelete}
            />
          ) : null}
        </div>
      </div>
    </div>
  )
}

export function ScrapePromptLibraryPanel({
  isOpen,
  onClose,
  prompts,
  selectedPromptId,
  activePromptId,
  editingPromptId,
  promptName,
  promptIntentText,
  promptEnabled,
  isPromptsLoading,
  isPromptSaving,
  isPromptDeleting,
  promptError,
  onSelectPrompt,
  onNewPrompt,
  onTogglePromptEnabled,
  onDeletePrompt,
  onActivatePrompt,
  onSaveAsNew,
  onUpdateCurrent,
  onSetPromptName,
  onSetPromptIntentText,
  onSetPromptEnabled,
  onRefresh,
}: ScrapePromptLibraryPanelProps) {
  const headerActions = (
    <Button variant="secondary" size="xs" onClick={onRefresh} loading={isPromptsLoading}>
      <IconRefresh size={14} />
    </Button>
  )

  const selectedPrompt = prompts.find((p) => p.id === selectedPromptId) ?? null
  const editingPrompt = prompts.find((p) => p.id === editingPromptId) ?? null
  const isEditingSystemDefault = Boolean(editingPrompt?.is_system_default)
  const headerMeta = selectedPrompt ? (
    <div className="flex flex-wrap items-center gap-2">
      {selectedPrompt.id === activePromptId && <Badge variant="success">Active for scraping</Badge>}
      <Badge variant={selectedPrompt.enabled ? 'success' : 'fail'}>
        {selectedPrompt.enabled ? 'Enabled' : 'Disabled'}
      </Badge>
      {selectedPrompt.is_system_default && <Badge variant="neutral">Default</Badge>}
    </div>
  ) : (
    <Badge variant="neutral">No scrape prompt selected</Badge>
  )

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title="Scrape Prompt Library"
      subtitle="Scraping prompts"
      size="lg"
      headerMeta={headerMeta}
      headerActions={headerActions}
    >
      <div className="flex h-full flex-col xl:flex-row">
        <aside className="flex-shrink-0 border-b border-[var(--oc-border)] p-4 xl:w-[300px] xl:border-b-0 xl:border-r xl:overflow-y-auto">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="text-sm font-bold">Saved scrape prompts</h3>
            <Button variant="secondary" size="xs" onClick={onNewPrompt}>
              <IconPlus size={13} />
              New
            </Button>
          </div>
          {isPromptsLoading && prompts.length === 0 ? (
            <PromptLibraryAsideSkeleton />
          ) : prompts.length === 0 ? (
            <PromptLibraryAsideEmpty message="No scrape prompts saved yet. Create one on the right." />
          ) : (
            <div className="space-y-2">
              {prompts.map((prompt) => (
                <ScrapePromptListItem
                  key={prompt.id}
                  prompt={prompt}
                  isEditing={editingPromptId === prompt.id}
                  isSelected={selectedPromptId === prompt.id}
                  isSaving={isPromptSaving}
                  isDeleting={isPromptDeleting}
                  activePromptId={activePromptId}
                  onSelect={() => onSelectPrompt(prompt)}
                  onToggleEnabled={() => onTogglePromptEnabled(prompt)}
                  onDelete={() => onDeletePrompt(prompt)}
                  onActivate={() => onActivatePrompt(prompt)}
                />
              ))}
            </div>
          )}
        </aside>

        <section className="flex-1 overflow-y-auto p-5">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-bold tracking-tight">
                {editingPromptId ? 'Edit scrape prompt' : 'New scrape prompt'}
              </h3>
              <p className="mt-0.5 text-xs text-[var(--oc-muted)]">
                Edit intent in plain English; compiled text and structured rules are generated.
              </p>
            </div>
            <span className="oc-kbd">{editingPromptId ? 'editing' : 'new draft'}</span>
          </div>

          <div className="space-y-4">
            <label className="block">
              <PromptEditorFieldLabel>Name</PromptEditorFieldLabel>
              <input
                type="text"
                value={promptName}
                onChange={(e) => onSetPromptName(e.target.value)}
                readOnly={isEditingSystemDefault}
                className="w-full rounded-xl border border-[var(--oc-border)] bg-white px-4 py-2.5 text-sm text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)] focus:ring-2 focus:ring-[var(--oc-accent)]/10"
                placeholder="S1 discovery prompt v2"
              />
            </label>

            <label className="block">
              <PromptEditorFieldLabel>Intent text</PromptEditorFieldLabel>
              <textarea
                value={promptIntentText}
                onChange={(e) => onSetPromptIntentText(e.target.value)}
                readOnly={isEditingSystemDefault}
                rows={6}
                className="w-full rounded-2xl border border-[var(--oc-border)] bg-white px-4 py-3 text-sm leading-6 text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)] focus:ring-2 focus:ring-[var(--oc-accent)]/10"
                placeholder="Find pricing, product, services, leadership, and contact pages from official site content."
              />
            </label>

            <label className="block">
              <PromptEditorFieldLabel>Compiled prompt (read-only)</PromptEditorFieldLabel>
              <textarea
                value={editingPrompt?.compiled_prompt_text ?? 'No compiled prompt available yet.'}
                readOnly
                rows={8}
                className="w-full rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] px-4 py-3 font-mono text-xs leading-6 text-[var(--oc-muted)] outline-none"
              />
            </label>

            <label className="block">
              <PromptEditorFieldLabel>Structured rules (read-only)</PromptEditorFieldLabel>
              <pre className="w-full overflow-x-auto whitespace-pre-wrap wrap-break-word rounded-2xl border border-(--oc-border) bg-(--oc-surface) px-4 py-3 font-mono text-xs leading-6 text-(--oc-muted)">
                {formatScrapeRulesPreview(editingPrompt?.scrape_rules_structured)}
              </pre>
            </label>

            <label className="flex cursor-pointer items-center gap-2.5">
              <input
                type="checkbox"
                checked={promptEnabled}
                onChange={(e) => onSetPromptEnabled(e.target.checked)}
                disabled={isEditingSystemDefault}
                className="h-4 w-4 rounded border-[var(--oc-border)] accent-[var(--oc-accent)]"
              />
              <span className="text-sm font-semibold text-[var(--oc-text)]">Enabled</span>
            </label>
            {isEditingSystemDefault && (
              <p className="text-xs text-[var(--oc-muted)]">
                System default scrape prompt is read-only.
              </p>
            )}
          </div>

          {promptError ? <PromptLibraryFormError message={promptError} /> : null}

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <Button variant="primary" size="md" onClick={onSaveAsNew} loading={isPromptSaving}>
              Save as new
            </Button>
            <Button
              variant="secondary"
              size="md"
              onClick={onUpdateCurrent}
              disabled={!editingPromptId || isPromptSaving || isEditingSystemDefault}
            >
              Update current
            </Button>
            {editingPrompt && (
              <Button
                variant="secondary"
                size="md"
                onClick={() => onActivatePrompt(editingPrompt)}
                disabled={isPromptSaving || !editingPrompt.enabled || editingPrompt.id === activePromptId || isEditingSystemDefault}
              >
                Set active
              </Button>
            )}
            <Button variant="ghost" size="md" onClick={onNewPrompt}>
              New blank
            </Button>
          </div>
        </section>
      </div>
    </Drawer>
  )
}
