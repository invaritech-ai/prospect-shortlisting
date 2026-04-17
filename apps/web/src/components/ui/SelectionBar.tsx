import type { ReactNode } from 'react'

interface SelectionBarProps {
  stageColor: string       // CSS var name, e.g. '--s1'
  stageBg: string          // CSS var name, e.g. '--s1-bg'
  selectedCount: number
  totalMatching: number | null   // null = hide "select all" link
  activeLetters: Set<string>
  onSelectAllMatching: (() => void) | null
  isSelectingAll: boolean
  onClear: () => void
  children: ReactNode
}

export function SelectionBar({
  stageColor,
  stageBg,
  selectedCount,
  totalMatching,
  activeLetters,
  onSelectAllMatching,
  isSelectingAll,
  onClear,
  children,
}: SelectionBarProps) {
  if (selectedCount === 0) return null

  const showSelectAll =
    onSelectAllMatching !== null &&
    totalMatching !== null &&
    selectedCount < totalMatching

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium"
      style={{
        backgroundColor: `var(${stageBg})`,
        borderLeft: `3px solid var(${stageColor})`,
        animation: 'sel-slide-in 120ms ease-out',
      }}
    >
      <span
        className="rounded-full px-2.5 py-0.5 text-xs font-bold text-white"
        style={{ backgroundColor: `var(${stageColor})` }}
      >
        {selectedCount.toLocaleString()}
      </span>

      {[...activeLetters].sort().map((l) => (
        <span
          key={l}
          className="rounded-full border px-2 py-0.5 text-[11px] font-bold uppercase"
          style={{ borderColor: `var(${stageColor})`, color: `var(${stageColor})` }}
        >
          {l}
        </span>
      ))}

      {showSelectAll && (
        <button
          type="button"
          onClick={onSelectAllMatching}
          disabled={isSelectingAll}
          className="text-xs underline underline-offset-2 transition hover:no-underline disabled:opacity-60"
          style={{ color: `var(${stageColor})` }}
        >
          {isSelectingAll ? 'Selecting…' : `Select all ${totalMatching?.toLocaleString()} matching`}
        </button>
      )}

      <span className="flex-1" />
      {children}

      <button
        type="button"
        onClick={onClear}
        className="ml-1 rounded-full p-1 text-xs leading-none transition hover:bg-black/10"
        aria-label="Clear selection"
      >
        ✕
      </button>
    </div>
  )
}
