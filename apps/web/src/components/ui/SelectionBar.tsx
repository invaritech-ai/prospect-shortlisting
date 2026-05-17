import type { ReactNode } from 'react'

interface SelectionBarProps {
  stageColor: string
  stageBg: string
  selectedCount: number
  totalMatching: number | null
  activeLetters: Set<string>
  onSelectAllMatching: (() => void) | null
  isSelectingAll: boolean
  onClear: () => void
  children: ReactNode
  disabled?: boolean
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
  disabled = false,
}: SelectionBarProps) {
  if (selectedCount === 0) return null

  const showSelectAll =
    onSelectAllMatching !== null &&
    totalMatching !== null &&
    selectedCount < totalMatching

  return (
    <div
      className="oc-selection-bar"
      style={{
        backgroundColor: `var(${stageBg})`,
        borderLeft: `3px solid var(${stageColor})`,
      }}
    >
      <span
        className="oc-selection-bar-count"
        style={{ backgroundColor: `var(${stageColor})` }}
      >
        {selectedCount.toLocaleString()}
      </span>

      {[...activeLetters].sort().map((l) => (
        <span
          key={l}
          className="oc-selection-bar-letter"
          style={{ borderColor: `var(${stageColor})`, color: `var(${stageColor})` }}
        >
          {l}
        </span>
      ))}

      {showSelectAll && (
        <button
          type="button"
          onClick={onSelectAllMatching}
          disabled={disabled || isSelectingAll}
          className="oc-selection-bar-select-all"
          style={{ color: `var(${stageColor})` }}
        >
          {isSelectingAll ? 'Selecting…' : `Select all ${totalMatching?.toLocaleString()} matching`}
        </button>
      )}

      <span style={{ flex: 1 }} />
      {children}

      <button
        type="button"
        onClick={onClear}
        disabled={disabled}
        className="oc-selection-bar-clear"
        aria-label="Clear selection"
      >
        ✕
      </button>
    </div>
  )
}
