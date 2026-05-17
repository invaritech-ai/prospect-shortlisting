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
    <div className="oc-toast-root" aria-live="polite" aria-atomic="true">
      {error && (
        <div className="oc-toast-error">
          <div className="oc-toast-icon oc-toast-icon-error">
            <IconX size={12} />
          </div>
          <p className="oc-toast-msg-error">{error}</p>
        </div>
      )}
      {notice && (
        <div className="oc-toast-success">
          <div className="oc-toast-content">
            <div className="oc-toast-icon oc-toast-icon-success">
              <IconCheck size={12} />
            </div>
            <p className="oc-toast-msg-success">{notice}</p>
          </div>
          {noticeAction ? (
            <button type="button" onClick={noticeAction.onClick} className="oc-toast-action">
              {noticeAction.label}
            </button>
          ) : null}
        </div>
      )}
    </div>
  )
}
