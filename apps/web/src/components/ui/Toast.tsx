import { IconX, IconCheck } from './icons'

interface ToastProps {
  error?: string
  notice?: string
}

export function Toast({ error, notice }: ToastProps) {
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
          <p className="text-sm font-medium text-rose-800">{error}</p>
        </div>
      )}
      {notice && (
        <div className="pointer-events-auto flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 shadow-lg">
          <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-emerald-200">
            <IconCheck size={12} className="text-emerald-700" />
          </div>
          <p className="text-sm font-medium text-emerald-800">{notice}</p>
        </div>
      )}
    </div>
  )
}
