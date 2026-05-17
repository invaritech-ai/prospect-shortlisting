import { useEffect, useId, useRef, type ReactNode } from 'react'
import { Button } from './Button'

interface ConfirmDialogProps {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel: string
  cancelLabel?: string
  confirmVariant?: 'primary' | 'danger'
  isConfirming?: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = 'Cancel',
  confirmVariant = 'primary',
  isConfirming = false,
  onClose,
  onConfirm,
}: ConfirmDialogProps) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    previouslyFocused.current = (document.activeElement as HTMLElement) ?? null
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); if (!isConfirming) onClose() }
    }
    document.addEventListener('keydown', onKeyDown)

    const t = window.setTimeout(() => {
      const focusable = panelRef.current?.querySelector<HTMLElement>(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      focusable?.focus()
    }, 0)

    return () => {
      window.clearTimeout(t)
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = prevOverflow
      previouslyFocused.current?.focus?.()
    }
  }, [open, onClose, isConfirming])

  if (!open) return null

  return (
    <div className="oc-confirm-root" role="presentation">
      <button
        type="button"
        aria-label="Close dialog"
        className="oc-confirm-backdrop"
        onClick={() => !isConfirming && onClose()}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="oc-confirm-dialog"
      >
        <h2 id={titleId} className="oc-confirm-title">{title}</h2>
        <div className="oc-confirm-body">{children}</div>
        <div className="oc-confirm-actions">
          <Button variant="secondary" size="sm" onClick={onClose} disabled={isConfirming}>
            {cancelLabel}
          </Button>
          <Button variant={confirmVariant} size="sm" loading={isConfirming} onClick={() => void onConfirm()}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
