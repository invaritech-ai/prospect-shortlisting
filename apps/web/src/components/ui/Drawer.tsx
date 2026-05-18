import { useEffect, type ReactNode } from 'react'
import { IconX } from './icons'

interface DrawerProps {
  isOpen: boolean
  onClose: () => void
  title: string
  subtitle?: string
  headerMeta?: ReactNode
  headerActions?: ReactNode
  footer?: ReactNode
  children: ReactNode
  size?: 'md' | 'lg'
  accentColor?: string
}

export function Drawer({
  isOpen,
  onClose,
  title,
  subtitle,
  headerMeta,
  headerActions,
  footer,
  children,
  size = 'md',
  accentColor,
}: DrawerProps) {
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const panelSizeClass = size === 'lg' ? 'oc-drawer-panel-lg' : 'oc-drawer-panel-md'

  return (
    <div className="oc-drawer-root">
      <button
        type="button"
        className="oc-drawer-backdrop"
        onClick={onClose}
        aria-label="Close"
      />

      <div
        className={`oc-drawer-panel ${panelSizeClass}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={accentColor ? { '--drawer-accent': accentColor } as React.CSSProperties : undefined}
      >
        <div className="oc-drawer-handle">
          <div className="oc-drawer-handle-bar" />
        </div>

        <div className="oc-drawer-header">
          <div className="oc-drawer-header-row">
            <div style={{ minWidth: 0 }}>
              {subtitle && <span className="oc-drawer-subtitle">{subtitle}</span>}
              <h2 className="oc-drawer-title">{title}</h2>
            </div>
            <div style={{ display: 'flex', flexShrink: 0, alignItems: 'center', gap: '0.5rem' }}>
              {headerActions}
              <button type="button" onClick={onClose} className="oc-drawer-close" aria-label="Close">
                <IconX size={16} />
              </button>
            </div>
          </div>
          {headerMeta && <div style={{ marginTop: '0.875rem' }}>{headerMeta}</div>}
        </div>

        <div className="oc-drawer-body">{children}</div>
        {footer && <div className="oc-drawer-footer">{footer}</div>}
      </div>
    </div>
  )
}
