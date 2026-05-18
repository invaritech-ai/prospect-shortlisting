import type { ActiveView } from '../../../lib/navigation'
import { LiveDot } from '../../ui/LiveDot'

interface StageNavItemProps {
  view: ActiveView
  label: string
  stageColor: string
  Icon: React.FC<{ size?: number; className?: string }>
  isActive: boolean
  count: number
  isLive: boolean
  collapsed: boolean
  onClick: () => void
}

export function StageNavItem({ view: _view, label, stageColor, Icon, isActive, count, isLive, collapsed, onClick }: StageNavItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={collapsed ? label : undefined}
      className="oc-nav-item"
      data-active={isActive ? 'true' : 'false'}
      style={{
        '--item-accent': stageColor,
        justifyContent: collapsed ? 'center' : undefined,
        position: 'relative',
      } as React.CSSProperties}
    >
      {/* Stage identity dot — always visible */}
      <span className="oc-stage-nav-dot" style={{ backgroundColor: stageColor }} />

      {/* Icon */}
      <Icon size={16} className="oc-icon-shrink" />

      {/* Label */}
      <span style={{
        flex: 1, overflow: 'hidden', whiteSpace: 'nowrap',
        transition: 'max-width 200ms, opacity 200ms',
        maxWidth: collapsed ? 0 : 200,
        opacity: collapsed ? 0 : 1,
        fontSize: '0.875rem',
      }}>
        {label}
      </span>

      {/* Live dot + count badge — only when expanded */}
      {!collapsed && (
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginLeft: 'auto', flexShrink: 0 }}>
          {isLive && <LiveDot color={stageColor} />}
          {count > 0 && (
            <span className="oc-nav-badge" style={{ backgroundColor: stageColor }}>
              {count > 999 ? `${Math.floor(count / 1000)}k` : count}
            </span>
          )}
        </span>
      )}

      {/* Collapsed: small dot indicator when there are items */}
      {collapsed && count > 0 && (
        <span style={{
          position: 'absolute', top: '6px', right: '6px',
          width: '6px', height: '6px', borderRadius: '9999px',
          backgroundColor: stageColor,
        }} />
      )}
    </button>
  )
}
