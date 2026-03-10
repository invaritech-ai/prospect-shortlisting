import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'xs' | 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
  loading?: boolean
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    'bg-[var(--oc-accent)] text-white border border-[var(--oc-accent)] hover:brightness-95 disabled:opacity-50',
  secondary:
    'bg-white text-[var(--oc-text)] border border-[var(--oc-border)] hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)] disabled:opacity-50',
  ghost:
    'bg-transparent text-[var(--oc-muted)] border border-transparent hover:bg-[var(--oc-accent-soft)] hover:text-[var(--oc-accent-ink)] disabled:opacity-50',
  danger:
    'bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-50',
}

const SIZE_CLASSES: Record<Size, string> = {
  xs: 'px-2.5 py-1 text-[11px] rounded-lg',
  sm: 'px-3 py-1.5 text-xs rounded-lg',
  md: 'px-4 py-2 text-sm rounded-xl',
}

export function Button({
  variant = 'secondary',
  size = 'sm',
  children,
  loading = false,
  className = '',
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-1.5 font-bold transition cursor-pointer disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {loading ? (
        <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent opacity-60" />
      ) : null}
      {children}
    </button>
  )
}
