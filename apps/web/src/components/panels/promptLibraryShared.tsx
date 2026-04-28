import { useState } from 'react'
import type { ReactNode } from 'react'
import { Skeleton } from '../ui/Skeleton'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { IconPlus, IconRefresh } from '../ui/icons'
import { promptListCardClassNames } from './promptLibraryStyles'

export function PromptLibraryRefreshButton({
  isLoading,
  onRefresh,
}: {
  isLoading: boolean
  onRefresh: () => void
}) {
  return (
    <Button variant="secondary" size="xs" onClick={onRefresh} loading={isLoading}>
      <IconRefresh size={14} />
    </Button>
  )
}

export function PromptEditorFieldLabel({ children }: { children: ReactNode }) {
  return (
    <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
      {children}
    </span>
  )
}

function PromptLibraryAsideSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-20 w-full rounded-2xl" />
      <Skeleton className="h-20 w-full rounded-2xl" />
      <Skeleton className="h-20 w-full rounded-2xl" />
    </div>
  )
}

function PromptLibraryAsideEmpty({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4">
      <p className="text-sm text-[var(--oc-muted)]">{message}</p>
    </div>
  )
}

export function PromptLibraryFormError({ message }: { message: string }) {
  return (
    <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3">
      <p className="text-sm font-medium text-rose-800">{message}</p>
    </div>
  )
}

export function PromptLibraryAside<TItem>({
  title,
  widthClassName,
  emptyMessage,
  isLoading,
  items,
  getItemKey,
  renderItem,
  onNewPrompt,
}: {
  title: string
  widthClassName: string
  emptyMessage: string
  isLoading: boolean
  items: TItem[]
  getItemKey: (item: TItem) => string
  renderItem: (item: TItem) => ReactNode
  onNewPrompt: () => void
}) {
  return (
    <aside className={`flex-shrink-0 border-b border-[var(--oc-border)] p-4 xl:border-b-0 xl:border-r xl:overflow-y-auto ${widthClassName}`}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-bold">{title}</h3>
        <Button variant="secondary" size="xs" onClick={onNewPrompt}>
          <IconPlus size={13} />
          New
        </Button>
      </div>
      {isLoading && items.length === 0 ? (
        <PromptLibraryAsideSkeleton />
      ) : items.length === 0 ? (
        <PromptLibraryAsideEmpty message={emptyMessage} />
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={getItemKey(item)}>{renderItem(item)}</div>
          ))}
        </div>
      )}
    </aside>
  )
}

export function PromptListItemCard({
  isEditing,
  name,
  meta,
  selectedLabel,
  onSelect,
  children,
}: {
  isEditing: boolean
  name: string
  meta: ReactNode
  selectedLabel: string | null
  onSelect: () => void
  children: ReactNode
}) {
  return (
    <div className={promptListCardClassNames(isEditing)}>
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-[var(--oc-accent-ink)]">{name}</p>
            <p className="mt-0.5 text-[11px] text-[var(--oc-muted)]">{meta}</p>
          </div>
          {selectedLabel ? <Badge variant="info">{selectedLabel}</Badge> : null}
        </div>
      </button>
      {children}
    </div>
  )
}

export function PromptEditorHeader({
  isEditing,
  editingTitle,
  newTitle,
  description,
}: {
  isEditing: boolean
  editingTitle: string
  newTitle: string
  description: string
}) {
  return (
    <div className="mb-5 flex items-center justify-between gap-3">
      <div>
        <h3 className="text-base font-bold tracking-tight">
          {isEditing ? editingTitle : newTitle}
        </h3>
        <p className="mt-0.5 text-xs text-[var(--oc-muted)]">{description}</p>
      </div>
      <span className="oc-kbd">{isEditing ? 'editing' : 'new draft'}</span>
    </div>
  )
}

export function PromptNameField({
  value,
  onChange,
  placeholder,
  readOnly = false,
}: {
  value: string
  onChange: (value: string) => void
  placeholder: string
  readOnly?: boolean
}) {
  return (
    <label className="block">
      <PromptEditorFieldLabel>Name</PromptEditorFieldLabel>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        className="w-full rounded-xl border border-[var(--oc-border)] bg-white px-4 py-2.5 text-sm text-[var(--oc-text)] outline-none transition focus:border-[var(--oc-accent)] focus:ring-2 focus:ring-[var(--oc-accent)]/10"
        placeholder={placeholder}
      />
    </label>
  )
}

export function PromptEnabledField({
  checked,
  onChange,
  disabled = false,
  helperText,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
  helperText?: string
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="h-4 w-4 rounded border-[var(--oc-border)] accent-[var(--oc-accent)]"
      />
      <span className="text-sm font-semibold text-[var(--oc-text)]">Enabled</span>
      {helperText ? <span className="text-xs text-[var(--oc-muted)]">{helperText}</span> : null}
    </label>
  )
}

export function DeleteConfirmButtonGroup({
  disabled,
  isDeleting,
  onConfirmDelete,
}: {
  disabled: boolean
  isDeleting: boolean
  onConfirmDelete: () => void
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (confirmDelete) {
    return (
      <>
        <button
          type="button"
          onClick={() => {
            setConfirmDelete(false)
            onConfirmDelete()
          }}
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
    )
  }

  return (
    <button
      type="button"
      onClick={() => setConfirmDelete(true)}
      disabled={disabled}
      className="rounded-lg border border-rose-200 px-2.5 py-1 text-[11px] font-bold text-rose-600 transition hover:border-rose-400 hover:bg-rose-50 disabled:opacity-50"
    >
      Delete
    </button>
  )
}
