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

// ── Decision-specific badge helpers ──────────────────────────────────────────

export function decisionVariant(decision: string | null): BadgeVariant {
  if (!decision) return 'neutral'
  const t = decision.trim().toLowerCase()
  if (t === 'possible') return 'success'
  if (t === 'unknown') return 'neutral'
  return 'fail' // crap
}

export function decisionBgClass(decision: string | null): string {
  if (!decision) return 'bg-slate-100 text-slate-600'
  const t = decision.trim().toLowerCase()
  if (t === 'possible') return 'bg-emerald-50 text-emerald-800'
  if (t === 'unknown') return 'bg-amber-50 text-amber-800'
  if (t === 'crap') return 'bg-rose-50 text-rose-800'
  return 'bg-indigo-50 text-indigo-800'
}
