import { useEffect, type ReactNode } from 'react'
import { IconX } from './icons'

interface DrawerProps {
  isOpen: boolean
  onClose: () => void
  title: string
  subtitle?: string
  headerMeta?: ReactNode   // badges, tabs, etc. below the title
  headerActions?: ReactNode // top-right area
  children: ReactNode
  size?: 'md' | 'lg'      // md=480px, lg=720px on desktop
}

export function Drawer({
  isOpen,
  onClose,
  title,
  subtitle,
  headerMeta,
  headerActions,
  children,
  size = 'md',
}: DrawerProps) {
  // ESC key closes
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const panelWidth = size === 'lg' ? 'md:w-[720px]' : 'md:w-[480px]'

  return (
    <div className="fixed inset-0 z-[var(--z-drawer)] flex items-end justify-end md:items-stretch">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-950/20 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel — bottom sheet on mobile, right slide on desktop */}
      <div
        className={`
          relative z-10 flex w-full flex-col overflow-hidden
          rounded-t-[28px] md:rounded-none
          max-h-[88vh] md:max-h-none md:h-full
          ${panelWidth}
          border-t border-[var(--oc-border)] md:border-t-0 md:border-l
          bg-[var(--oc-surface-strong)]
          shadow-[0_-8px_40px_rgba(10,31,24,0.12)] md:shadow-[-8px_0_40px_rgba(10,31,24,0.12)]
        `}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {/* Drag handle (mobile) */}
        <div className="flex justify-center pt-3 pb-1 md:hidden">
          <div className="h-1 w-10 rounded-full bg-[var(--oc-border)]" />
        </div>

        {/* Header */}
        <div className="border-b border-[var(--oc-border)] px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {subtitle && (
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--oc-muted)]">
                  {subtitle}
                </p>
              )}
              <h2 className="text-xl font-extrabold tracking-tight text-[var(--oc-text)] md:text-2xl">
                {title}
              </h2>
            </div>
            <div className="flex flex-shrink-0 items-center gap-2">
              {headerActions}
              <button
                type="button"
                onClick={onClose}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                aria-label="Close"
              >
                <IconX size={16} />
              </button>
            </div>
          </div>
          {headerMeta && <div className="mt-3">{headerMeta}</div>}
        </div>

        {/* Scrollable body */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          {children}
        </div>
      </div>
    </div>
  )
}
