import type { ReactNode } from 'react'

interface NavSectionProps {
  label: string
  collapsed: boolean
  children: ReactNode
}

export function NavSection({ label, collapsed, children }: NavSectionProps) {
  return (
    <div>
      {!collapsed && <span className="oc-nav-section-label">{label}</span>}
      {collapsed && <div style={{ height: '0.75rem' }} />}
      {children}
    </div>
  )
}
