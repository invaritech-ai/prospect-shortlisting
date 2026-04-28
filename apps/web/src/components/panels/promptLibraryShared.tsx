import { useState } from 'react'
import type { ReactNode } from 'react'
import { Skeleton } from '../ui/Skeleton'

export function promptListCardClassNames(isEditing: boolean): string {
  return `rounded-2xl border p-3 transition ${
    isEditing
      ? 'border-[var(--oc-accent)] bg-[var(--oc-accent-soft)]/40'
      : 'border-[var(--oc-border)] bg-[var(--oc-surface)]'
  }`
}

export function PromptEditorFieldLabel({ children }: { children: ReactNode }) {
  return (
    <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
      {children}
    </span>
  )
}

export function PromptLibraryAsideSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-20 w-full rounded-2xl" />
      <Skeleton className="h-20 w-full rounded-2xl" />
      <Skeleton className="h-20 w-full rounded-2xl" />
    </div>
  )
}

export function PromptLibraryAsideEmpty({ message }: { message: string }) {
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
