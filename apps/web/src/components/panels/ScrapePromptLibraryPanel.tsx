import type { ScrapePromptRead, ScrapeRules } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import {
  DeleteConfirmButtonGroup,
  PromptEnabledField,
  PromptEditorFieldLabel,
  PromptEditorHeader,
  PromptLibraryAside,
  PromptLibraryFormError,
  PromptLibraryRefreshButton,
  PromptListItemCard,
  PromptNameField,
} from './promptLibraryShared'

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
    <PromptListItemCard
      isEditing={isEditing}
      name={prompt.name}
      meta={<>Updated {parseUTC(prompt.updated_at).toLocaleString()}</>}
      selectedLabel={isSelected ? 'Selected' : null}
      onSelect={onSelect}
    >
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
    </PromptListItemCard>
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
  const headerActions = <PromptLibraryRefreshButton isLoading={isPromptsLoading} onRefresh={onRefresh} />

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
        <PromptLibraryAside
          title="Saved scrape prompts"
          widthClassName="xl:w-[300px]"
          emptyMessage="No scrape prompts saved yet. Create one on the right."
          isLoading={isPromptsLoading}
          items={prompts}
          getItemKey={(prompt) => prompt.id}
          onNewPrompt={onNewPrompt}
          renderItem={(prompt) => (
            <ScrapePromptListItem
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
          )}
        />

        <section className="flex-1 overflow-y-auto p-5">
          <PromptEditorHeader
            isEditing={Boolean(editingPromptId)}
            editingTitle="Edit scrape prompt"
            newTitle="New scrape prompt"
            description="Edit intent in plain English; compiled text and structured rules are generated."
          />

          <div className="space-y-4">
            <PromptNameField
              value={promptName}
              onChange={onSetPromptName}
              placeholder="S1 discovery prompt v2"
              readOnly={isEditingSystemDefault}
            />

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

            <PromptEnabledField
              checked={promptEnabled}
              onChange={onSetPromptEnabled}
              disabled={isEditingSystemDefault}
            />
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
