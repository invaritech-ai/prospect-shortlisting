import { Button } from './Button'
import { IconTrash, IconGlobe, IconZap, IconX, IconUsers } from './icons'
import type { PromptRead } from '../../lib/types'

interface BulkActionBarProps {
  selectedCount: number
  onClearSelection: () => void
  onScrapeSelected: () => void
  onClassifySelected: () => void
  onDeleteSelected: () => void
  onSelectAllFiltered: () => void
  onFetchContactsSelected: () => void
  isScrapingSelected: boolean
  isClassifyingSelected: boolean
  isDeleting: boolean
  isSelectingAll: boolean
  isFetchingContactsSelected: boolean
  selectedPrompt: PromptRead | null
}

export function BulkActionBar({
  selectedCount,
  onClearSelection,
  onScrapeSelected,
  onClassifySelected,
  onDeleteSelected,
  onSelectAllFiltered,
  onFetchContactsSelected,
  isScrapingSelected,
  isClassifyingSelected,
  isDeleting,
  isSelectingAll,
  isFetchingContactsSelected,
  selectedPrompt,
}: BulkActionBarProps) {
  if (selectedCount === 0) return null

  const canClassify = !!selectedPrompt?.enabled

  return (
    <div
      className="
        fixed bottom-[calc(var(--oc-bottom-nav-h)+10px)] left-4 right-4 z-[var(--z-bulk-bar)]
        md:bottom-6 md:left-1/2 md:right-auto md:-translate-x-1/2 md:w-auto
      "
      aria-label={`${selectedCount} companies selected`}
    >
      <div
        className="
          flex flex-wrap items-center justify-between gap-2 rounded-2xl
          border border-[var(--oc-accent)] bg-[var(--oc-accent-ink)]
          px-4 py-3 shadow-[0_8px_32px_rgba(10,31,24,0.28)]
        "
      >
        {/* Count pill */}
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-[11px] font-bold text-white">
            {selectedCount} selected
          </span>
          <button
            type="button"
            onClick={onClearSelection}
            className="rounded p-0.5 text-white/60 transition hover:text-white"
            aria-label="Clear selection"
          >
            <IconX size={14} />
          </button>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="xs"
            className="!border-white/20 !text-white hover:!bg-white/15"
            onClick={onSelectAllFiltered}
            loading={isSelectingAll}
          >
            Select all matching
          </Button>
          <Button
            variant="ghost"
            size="xs"
            className="!border-white/20 !text-white hover:!bg-white/15"
            onClick={onScrapeSelected}
            loading={isScrapingSelected}
          >
            <IconGlobe size={14} />
            Scrape
          </Button>
          <Button
            variant="ghost"
            size="xs"
            className="!border-white/20 !text-white hover:!bg-white/15 disabled:!opacity-40"
            onClick={onClassifySelected}
            loading={isClassifyingSelected}
            disabled={!canClassify}
            title={canClassify ? undefined : 'Select an enabled prompt first'}
          >
            <IconZap size={14} />
            Classify
          </Button>
          <Button
            variant="ghost"
            size="xs"
            className="!border-white/20 !text-white hover:!bg-white/15"
            onClick={onFetchContactsSelected}
            loading={isFetchingContactsSelected}
          >
            <IconUsers size={14} />
            Contacts
          </Button>
          <Button
            variant="ghost"
            size="xs"
            className="!border-rose-400/30 !text-rose-300 hover:!bg-rose-500/20"
            onClick={onDeleteSelected}
            loading={isDeleting}
          >
            <IconTrash size={14} />
            Delete
          </Button>
        </div>
      </div>
    </div>
  )
}
