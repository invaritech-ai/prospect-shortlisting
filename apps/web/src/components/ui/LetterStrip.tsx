const LETTERS = 'abcdefghijklmnopqrstuvwxyz'.split('')

interface LetterStripProps {
  active: string | null
  counts: Record<string, number>
  onChange: (letter: string | null) => void
}

export function LetterStrip({ active, counts, onChange }: LetterStripProps) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto py-0.5 -mx-1 px-1 scrollbar-none">
      {/* All pill */}
      <button
        type="button"
        onClick={() => onChange(null)}
        className={`flex-shrink-0 rounded-full px-3 py-1 text-[11px] font-bold transition ${
          active === null
            ? 'bg-(--oc-accent) text-white'
            : 'border border-(--oc-border) text-(--oc-muted) hover:border-(--oc-accent) hover:text-(--oc-accent)'
        }`}
      >
        All
      </button>

      {LETTERS.map((letter) => {
        const count = counts[letter] ?? 0
        const isActive = active === letter
        const isEmpty = count === 0
        return (
          <button
            key={letter}
            type="button"
            disabled={isEmpty}
            onClick={() => onChange(isActive ? null : letter)}
            className={`flex-shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase transition ${
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
  )
}
