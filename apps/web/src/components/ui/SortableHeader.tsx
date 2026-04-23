interface SortableHeaderProps {
  label: string
  field: string
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
  className?: string
  disabled?: boolean
}

export function SortableHeader({ label, field, sortBy, sortDir, onSort, className = '', disabled = false }: SortableHeaderProps) {
  const active = sortBy === field
  return (
    <th
      className={`p-3 text-left font-semibold select-none whitespace-nowrap ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} ${className}`}
      onClick={() => { if (!disabled) onSort(field) }}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <span className="inline-flex flex-col leading-none text-[9px]" style={{ opacity: active ? 1 : 0.3 }}>
          <span style={{ color: active && sortDir === 'asc' ? 'var(--oc-accent)' : undefined }}>▲</span>
          <span style={{ color: active && sortDir === 'desc' ? 'var(--oc-accent)' : undefined }}>▼</span>
        </span>
      </span>
    </th>
  )
}
