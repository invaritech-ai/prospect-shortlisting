import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'xs' | 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
  loading?: boolean
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
      className={`oc-btn oc-btn-${variant} oc-btn-${size} ${className}`}
      {...rest}
    >
      {loading ? (
        <span
          style={{
            display: 'inline-block',
            width: '0.875rem',
            height: '0.875rem',
            borderRadius: '9999px',
            border: '2px solid currentColor',
            borderTopColor: 'transparent',
            animation: 'spin 0.7s linear infinite',
            opacity: 0.6,
          }}
        />
      ) : null}
      {children}
    </button>
  )
}
