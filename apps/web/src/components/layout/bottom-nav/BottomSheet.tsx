import type { ActiveView } from '../../../lib/navigation'
import { LiveDot } from '../../ui/LiveDot'

export interface SheetItem {
  view: ActiveView
  label: string
  Icon: React.FC<{ size?: number; className?: string }>
  stageColor?: string
  count?: number
  isLive?: boolean
}

interface BottomSheetProps {
  items: SheetItem[]
  activeView: ActiveView
  onNavigate: (view: ActiveView) => void
  onClose: () => void
}

export function BottomSheet({ items, activeView, onNavigate, onClose }: BottomSheetProps) {
  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 md:hidden"
        style={{ zIndex: 'var(--z-overlay)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sheet */}
      <div className="oc-bottom-sheet md:hidden" role="menu">
        <div className="oc-bottom-sheet-handle">
          <div className="oc-bottom-sheet-handle-bar" />
        </div>

        {items.map((item) => {
          const isActive = activeView === item.view
          const accent   = item.stageColor ?? 'var(--oc-accent)'

          return (
            <button
              key={item.view}
              type="button"
              role="menuitem"
              className="oc-bottom-sheet-item"
              data-active={isActive ? 'true' : 'false'}
              style={{ '--item-accent': accent } as React.CSSProperties}
              onClick={() => { onNavigate(item.view); onClose() }}
            >
              {/* Stage colour dot for pipeline items */}
              {item.stageColor && (
                <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: item.stageColor, flexShrink: 0 }} />
              )}

              {/* Icon */}
              <span style={{ color: isActive ? accent : 'var(--oc-muted)', flexShrink: 0, display: 'flex' }}>
                <item.Icon size={20} />
              </span>

              {/* Label */}
              <span style={{ flex: 1, fontSize: '1rem', fontWeight: isActive ? 600 : 500, color: isActive ? accent : 'var(--oc-text)' }}>
                {item.label}
              </span>

              {/* Live dot + count badge */}
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', flexShrink: 0 }}>
                {item.isLive && <LiveDot color={item.stageColor ?? 'var(--oc-accent)'} />}
                {item.count != null && item.count > 0 && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', fontWeight: 700,
                    padding: '0.1875rem 0.5rem', borderRadius: '9999px', color: '#fff',
                    backgroundColor: item.stageColor ?? 'var(--oc-accent)',
                  }}>
                    {item.count > 999 ? `${Math.floor(item.count / 1000)}k` : item.count}
                  </span>
                )}
              </span>
            </button>
          )
        })}
      </div>
    </>
  )
}
