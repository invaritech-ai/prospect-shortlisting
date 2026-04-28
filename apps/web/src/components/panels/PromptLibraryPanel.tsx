import type { PromptRead } from '../../lib/types'
import { parseUTC } from '../../lib/api'
import { Drawer } from '../ui/Drawer'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import {
  DeleteConfirmButtonGroup,
  PromptEnabledField,
  PromptEditorFieldLabel,
  PromptEditorHeader,
  PromptLibraryFormError,
  PromptLibraryAside,
  PromptLibraryRefreshButton,
  PromptListItemCard,
  PromptNameField,
} from './promptLibraryShared'

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
  onSetPromptEnabled: (v: boolean) => void
  onRefresh: () => void
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
  return (
    <PromptListItemCard
      isEditing={isEditing}
      name={prompt.name}
      meta={
        <>
          {parseUTC(prompt.created_at).toLocaleString()} ·{' '}
          <span className="font-medium">
            {prompt.run_count} run{prompt.run_count !== 1 ? 's' : ''}
          </span>
        </>
      }
      selectedLabel={isSelected ? 'Active' : null}
      onSelect={onSelect}
    >
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
          <DeleteConfirmButtonGroup
            disabled={isSaving || isDeleting}
            isDeleting={isDeleting}
            onConfirmDelete={onDelete}
          />
        </div>
      </div>
    </PromptListItemCard>
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
  onSetPromptEnabled,
  onRefresh,
}: PromptLibraryPanelProps) {
  const headerActions = <PromptLibraryRefreshButton isLoading={isPromptsLoading} onRefresh={onRefresh} />

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
        <PromptLibraryAside
          title="Saved prompts"
          widthClassName="xl:w-[280px]"
          emptyMessage="No prompts saved yet. Create one on the right."
          isLoading={isPromptsLoading}
          items={prompts}
          getItemKey={(prompt) => prompt.id}
          onNewPrompt={onNewPrompt}
          renderItem={(prompt) => (
            <PromptListItem
              prompt={prompt}
              isEditing={editingPromptId === prompt.id}
              isSelected={selectedPromptId === prompt.id}
              isSaving={isPromptSaving}
              isDeleting={isPromptDeleting}
              onSelect={() => onSelectPrompt(prompt)}
              onToggleEnabled={() => onTogglePromptEnabled(prompt)}
              onDelete={() => onDeletePrompt(prompt)}
            />
          )}
        />

        {/* Editor */}
        <section className="flex-1 overflow-y-auto p-5">
          <PromptEditorHeader
            isEditing={Boolean(editingPromptId)}
            editingTitle="Edit prompt"
            newTitle="New prompt"
            description="Save as new to preserve history. Update only for minor corrections."
          />

          <div className="space-y-4">
            <PromptNameField
              value={promptName}
              onChange={onSetPromptName}
              placeholder="Supplier fit rubric v1"
            />

            <label className="block">
              <PromptEditorFieldLabel>Prompt text</PromptEditorFieldLabel>
              <textarea
                value={promptText}
                onChange={(e) => onSetPromptText(e.target.value)}
                rows={16}
                className="min-h-[280px] w-full rounded-2xl border border-[var(--oc-border)] bg-white px-4 py-3 font-mono text-xs leading-6 text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)] focus:ring-2 focus:ring-[var(--oc-accent)]/10 md:min-h-[360px]"
                placeholder="Paste or write the rubric prompt here."
              />
            </label>

            <PromptEnabledField
              checked={promptEnabled}
              onChange={onSetPromptEnabled}
              helperText="(disabled prompts won't be used for new runs)"
            />
          </div>

          {promptError ? <PromptLibraryFormError message={promptError} /> : null}

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
