const LETTERS = 'abcdefghijklmnopqrstuvwxyz'.split('')

interface LetterStripProps {
  // Single-select mode (existing callers)
  active?: string | null
  onChange?: (letter: string | null) => void
  // Multi-select mode (new pipeline views)
  multiSelect?: boolean
  activeLetters?: Set<string>
  onToggle?: (letter: string) => void
  onClear?: () => void
  // Shared
  counts: Record<string, number>
}

export function LetterStrip({
  active,
  onChange,
  multiSelect = false,
  activeLetters,
  onToggle,
  onClear,
  counts,
}: LetterStripProps) {
  const isAllActive = multiSelect
    ? (activeLetters?.size ?? 0) === 0
    : active === null

  return (
    <div className="relative -mx-1">
      {/* Fade hint on right edge indicating scrollability */}
      <div className="pointer-events-none absolute right-0 top-0 h-full w-8 bg-linear-to-l from-white/80 to-transparent z-10" />
      <div className="flex items-center gap-1 overflow-x-auto py-0.5 px-1 scrollbar-none" style={{ touchAction: 'pan-x', WebkitOverflowScrolling: 'touch' } as React.CSSProperties}>
        <button
          type="button"
          onClick={() => (multiSelect ? onClear?.() : onChange?.(null))}
          className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-bold transition ${
            isAllActive
              ? 'bg-(--oc-accent) text-white'
              : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--oc-accent) hover:text-(--oc-accent)'
          }`}
        >
          All
        </button>

        {LETTERS.map((letter) => {
          const count = counts[letter] ?? 0
          const isActive = multiSelect
            ? (activeLetters?.has(letter) ?? false)
            : active === letter
          const isEmpty = count === 0

          return (
            <button
              key={letter}
              type="button"
              disabled={isEmpty}
              onClick={() =>
                multiSelect ? onToggle?.(letter) : onChange?.(isActive ? null : letter)
              }
              className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase transition ${
                isActive
                  ? 'bg-(--oc-accent) text-white'
                  : isEmpty
                    ? 'text-(--oc-border) cursor-not-allowed'
                    : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--oc-accent) hover:text-(--oc-accent)'
              }`}
            >
              {letter.toUpperCase()}
            </button>
          )
        })}
      </div>
    </div>
  )
}
