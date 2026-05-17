interface LiveDotProps {
  color: string
  size?: 'sm' | 'md'
}

export function LiveDot({ color, size = 'sm' }: LiveDotProps) {
  const dim = size === 'md' ? '0.625rem' : '0.5rem'
  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: dim, height: dim, flexShrink: 0 }}>
      <span style={{
        position: 'absolute', inset: 0, borderRadius: '9999px',
        backgroundColor: color, opacity: 0.5,
        animation: 'oc-ping 1.4s cubic-bezier(0,0,0.2,1) infinite',
      }} />
      <span style={{ position: 'relative', width: dim, height: dim, borderRadius: '9999px', backgroundColor: color }} />
    </span>
  )
}
