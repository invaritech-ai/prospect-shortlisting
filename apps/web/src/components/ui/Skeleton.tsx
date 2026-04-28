export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`oc-skeleton ${className}`} aria-hidden="true" />
}

export function SkeletonTable({ rows = 6 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--oc-border)]">
      <div className="border-b border-[var(--oc-border)] bg-white/70 px-3 py-2">
        <div className="flex gap-4">
          <Skeleton className="h-3 w-10" />
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-3 w-28 ml-auto" />
        </div>
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 border-t border-[var(--oc-border)] px-3 py-2">
          <Skeleton className="h-4 w-4 rounded flex-shrink-0" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-5 w-20 rounded-full" />
          <Skeleton className="h-5 w-16 rounded-full" />
          <div className="ml-auto flex gap-2">
            <Skeleton className="h-7 w-16 rounded-lg" />
            <Skeleton className="h-7 w-20 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  )
}
