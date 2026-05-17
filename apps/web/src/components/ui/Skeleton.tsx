export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`oc-skeleton ${className}`} aria-hidden="true" />
}

export function SkeletonTable({ rows = 6 }: { rows?: number }) {
  return (
    <div className="oc-skeleton-table">
      <div className="oc-skeleton-table-header">
        <Skeleton className="h-3 w-10" />
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-20" />
        <div style={{ marginLeft: 'auto' }}><Skeleton className="h-3 w-28" /></div>
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="oc-skeleton-table-row">
          <Skeleton className="h-4 w-4 rounded flex-shrink-0" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem' }}>
            <Skeleton className="h-7 w-16 rounded-lg" />
            <Skeleton className="h-7 w-20 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  )
}
