import { IconX, IconCheck } from './icons'

export interface ToastNoticeAction {
  label: string
  onClick: () => void
}

interface ToastProps {
  error?: string
  notice?: string
  noticeAction?: ToastNoticeAction | null
}

export function Toast({ error, notice, noticeAction }: ToastProps) {
  if (!error && !notice) return null

  return (
    <div
      className="pointer-events-none fixed bottom-[calc(var(--oc-bottom-nav-h)+12px)] left-4 right-4 z-[var(--z-toast)] md:bottom-4 md:left-auto md:right-6 md:w-96"
      aria-live="polite"
      aria-atomic="true"
    >
      {error && (
        <div className="pointer-events-auto flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 shadow-lg">
          <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-rose-200">
            <IconX size={12} className="text-rose-700" />
          </div>
          <p className="min-w-0 flex-1 text-sm font-medium text-rose-800">{error}</p>
        </div>
      )}
      {notice && (
        <div className="pointer-events-auto flex flex-col gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 shadow-lg sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-emerald-200">
              <IconCheck size={12} className="text-emerald-700" />
            </div>
            <p className="text-sm font-medium text-emerald-800">{notice}</p>
          </div>
          {noticeAction ? (
            <button
              type="button"
              onClick={noticeAction.onClick}
              className="shrink-0 rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-bold text-emerald-900 shadow-sm transition hover:bg-emerald-100"
            >
              {noticeAction.label}
            </button>
          ) : null}
        </div>
      )}
    </div>
  )
}
