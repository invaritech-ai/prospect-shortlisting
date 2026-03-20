import type { ReactNode } from 'react'

export type BadgeVariant = 'neutral' | 'info' | 'success' | 'fail'

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  neutral: 'oc-badge-neutral',
  info: 'oc-badge-info',
  success: 'oc-badge-success',
  fail: 'oc-badge-fail',
}

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
  title?: string
}

export function Badge({ variant = 'neutral', children, className = '', title }: BadgeProps) {
  return (
    <span className={`oc-badge ${VARIANT_CLASSES[variant]} ${className}`} title={title}>
      {children}
    </span>
  )
}
