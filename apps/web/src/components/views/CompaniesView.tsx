import type { DragEvent, FormEvent } from 'react'
import type {
  CompanyList,
  CompanyListItem,
  CompanyCounts,
  DecisionFilter,
  ScrapeFilter,
  PromptRead,
} from '../../lib/types'
import { Badge, decisionBgClass } from '../ui/Badge'
import { Button } from '../ui/Button'
import { BulkActionBar } from '../ui/BulkActionBar'
import { SkeletonRows } from '../ui/Skeleton'
import {
  IconChevronLeft,
  IconChevronRight,
  IconUpload,
  IconGlobe,
  IconZap,
} from '../ui/icons'

// ── Types ──────────────────────────────────────────────────────────────────

interface CompaniesViewProps {
  companies: CompanyList | null
  isLoading: boolean
  companyOffset: number
  pageSize: number
  decisionFilter: DecisionFilter
  scrapeFilter: ScrapeFilter
  selectedCompanyIds: string[]
  companyCounts: CompanyCounts | null
  actionState: Record<string, string>
  analysisActionState: Record<string, string>
  isScrapingSelected: boolean
  isScrapingAll: boolean
  isClassifyingSelected: boolean
  isClassifyingAll: boolean
  isDeleting: boolean
  isSelectingAll: boolean
  isUploading: boolean
  isDragActive: boolean
  file: File | null
  selectedPrompt: PromptRead | null
  utilitiesOpen: boolean
  onSetDecisionFilter: (f: DecisionFilter) => void
  onSetScrapeFilter: (f: ScrapeFilter) => void
  onSetPageSize: (size: number) => void
  onPagePrev: () => void
  onPageNext: () => void
  onToggleCompanySelection: (id: string) => void
  onToggleVisibleSelection: () => void
  onSelectAllFiltered: () => void
  onClearSelection: () => void
  onScrape: (company: CompanyListItem) => void
  onScrapeSelected: () => void
  onScrapeAll: () => void
  onClassify: (company: CompanyListItem) => void
  onClassifySelected: () => void
  onClassifyAll: () => void
  onDeleteSelected: () => void
  onSetFile: (file: File | null) => void
  onSetIsDragActive: (active: boolean) => void
  onUpload: (event: FormEvent<HTMLFormElement>) => void
  onToggleUtilities: () => void
}

// ── Constants ──────────────────────────────────────────────────────────────

const PAGE_SIZE_OPTIONS = [50, 100, 200] as const

const DECISION_FILTERS: Array<{ value: DecisionFilter; label: string; countKey: keyof CompanyCounts }> = [
  { value: 'all', label: 'All', countKey: 'total' },
  { value: 'unlabeled', label: 'No label', countKey: 'unlabeled' },
  { value: 'possible', label: 'Possible', countKey: 'possible' },
  { value: 'unknown', label: 'Unknown', countKey: 'unknown' },
  { value: 'crap', label: 'Crap', countKey: 'crap' },
]

const SCRAPE_FILTERS: Array<{ value: ScrapeFilter; label: string; countKey: keyof CompanyCounts }> = [
  { value: 'all', label: 'Any', countKey: 'total' },
  { value: 'done', label: 'Done', countKey: 'scrape_done' },
  { value: 'failed', label: 'Failed', countKey: 'scrape_failed' },
  { value: 'none', label: 'Not scraped', countKey: 'not_scraped' },
]

// ── Badge helpers ──────────────────────────────────────────────────────────

function scrapeBadgeForCompany(item: CompanyListItem): { label: string; variant: 'neutral' | 'info' | 'success' | 'fail'; title: string } {
  const status = item.latest_scrape_status ?? 'not_started'
  const stage1 = item.latest_scrape_stage1_status ?? '-'
  const stage2 = item.latest_scrape_stage2_status ?? '-'
  const title = `status: ${status} | stage1: ${stage1} | stage2: ${stage2}`
  if (!item.latest_scrape_status) return { label: 'Not started', variant: 'neutral', title }
  if (item.latest_scrape_terminal === false) {
    if (stage1 === 'running') return { label: 'Stage 1', variant: 'info', title }
    if (stage2 === 'running') return { label: 'Stage 2', variant: 'info', title }
    return { label: 'Running', variant: 'info', title }
  }
  if (status.includes('failed') || stage1 === 'failed' || stage2 === 'failed') {
    return { label: 'Failed', variant: 'fail', title }
  }
  if (status === 'completed' || stage2 === 'completed') return { label: 'Done', variant: 'success', title }
  return { label: 'Queued', variant: 'neutral', title }
}

// ── Sub-components ─────────────────────────────────────────────────────────

function FilterBar({
  decisionFilter,
  scrapeFilter,
  companyCounts,
  onSetDecisionFilter,
  onSetScrapeFilter,
}: Pick<CompaniesViewProps, 'decisionFilter' | 'scrapeFilter' | 'companyCounts' | 'onSetDecisionFilter' | 'onSetScrapeFilter'>) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {/* Decision filters */}
      <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)] mr-0.5">Decision</span>
      {DECISION_FILTERS.map((item) => {
        const count = companyCounts?.[item.countKey]
        const isActive = decisionFilter === item.value
        return (
          <button
            key={item.value}
            type="button"
            onClick={() => onSetDecisionFilter(item.value)}
            className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
              isActive
                ? 'bg-[var(--oc-accent)] text-white'
                : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
            }`}
          >
            {item.label}
            {count !== undefined && (
              <span className={`ml-1.5 rounded px-1 text-[10px] font-semibold ${isActive ? 'bg-white/20' : 'bg-slate-100 text-slate-500'}`}>
                {count.toLocaleString()}
              </span>
            )}
          </button>
        )
      })}

      <span className="h-4 w-px bg-[var(--oc-border)] mx-1" />

      {/* Scrape filters */}
      <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)] mr-0.5">Scrape</span>
      {SCRAPE_FILTERS.map((item) => {
        const count = companyCounts?.[item.countKey]
        const isActive = scrapeFilter === item.value
        return (
          <button
            key={item.value}
            type="button"
            onClick={() => onSetScrapeFilter(item.value)}
            className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
              isActive
                ? 'bg-slate-700 text-white'
                : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
            }`}
          >
            {item.label}
            {count !== undefined && (
              <span className={`ml-1.5 rounded px-1 text-[10px] font-semibold ${isActive ? 'bg-white/20' : 'bg-slate-100 text-slate-500'}`}>
                {count.toLocaleString()}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

function Pager({
  rangeLabel,
  canPrev,
  canNext,
  onPrev,
  onNext,
  pageSize,
  onSetPageSize,
}: {
  rangeLabel: string
  canPrev: boolean
  canNext: boolean
  onPrev: () => void
  onNext: () => void
  pageSize: number
  onSetPageSize: (n: number) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--oc-muted)]">
        Rows
        <select
          value={pageSize}
          onChange={(e) => onSetPageSize(Number(e.target.value))}
          className="rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1 text-xs font-semibold text-[var(--oc-text)]"
        >
          {PAGE_SIZE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <button
        type="button"
        onClick={onPrev}
        disabled={!canPrev}
        className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white text-[var(--oc-text)] transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="Previous page"
      >
        <IconChevronLeft size={16} />
      </button>
      <span className="oc-kbd">{rangeLabel}</span>
      <button
        type="button"
        onClick={onNext}
        disabled={!canNext}
        className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--oc-border)] bg-white text-[var(--oc-text)] transition hover:bg-[var(--oc-accent-soft)] disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="Next page"
      >
        <IconChevronRight size={16} />
      </button>
    </div>
  )
}

function IngestPanel({
  file,
  isDragActive,
  isUploading,
  onSetFile,
  onSetIsDragActive,
  onUpload,
}: Pick<CompaniesViewProps, 'file' | 'isDragActive' | 'isUploading' | 'onSetFile' | 'onSetIsDragActive' | 'onUpload'>) {
  const onDragOver = (e: DragEvent<HTMLLabelElement>) => { e.preventDefault(); onSetIsDragActive(true) }
  const onDragLeave = (e: DragEvent<HTMLLabelElement>) => { e.preventDefault(); onSetIsDragActive(false) }
  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    onSetIsDragActive(false)
    const f = e.dataTransfer.files?.[0]
    if (f) onSetFile(f)
  }

  return (
    <form
      onSubmit={onUpload}
      className="mt-3 rounded-2xl border border-[var(--oc-border)] bg-[var(--oc-surface)] p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <h3 className="text-sm font-bold">Ingest File</h3>
          <p className="mt-0.5 text-xs text-[var(--oc-muted)]">CSV, TXT, XLS, or XLSX with company URLs.</p>
        </div>
        <span className="oc-kbd">utility</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label
          htmlFor="upload-file"
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={`flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed px-4 py-4 transition ${
            isDragActive
              ? 'border-[var(--oc-accent)] bg-white shadow-[0_0_0_4px_rgba(15,118,110,0.08)]'
              : 'border-[var(--oc-border)] bg-white hover:border-[var(--oc-accent)]'
          }`}
        >
          <input
            id="upload-file"
            type="file"
            accept=".csv,.txt,.xls,.xlsx"
            className="hidden"
            onChange={(e) => onSetFile(e.target.files?.[0] ?? null)}
          />
          <IconUpload size={20} className="flex-shrink-0 text-[var(--oc-accent)]" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-[var(--oc-accent-ink)]">
              {file ? file.name : isDragActive ? 'Drop here' : 'Choose or drop a file'}
            </p>
            <p className="text-xs text-[var(--oc-muted)]">Table refreshes after parse completes.</p>
          </div>
        </label>
        <Button
          variant="primary"
          size="md"
          type="submit"
          disabled={!file || isUploading}
          loading={isUploading}
        >
          {isUploading ? 'Uploading…' : 'Upload & Parse'}
        </Button>
      </div>
    </form>
  )
}

// ── Mobile card ────────────────────────────────────────────────────────────

function CompanyCard({
  item,
  isSelected,
  onToggle,
  onScrape,
  onClassify,
  actionState,
  analysisActionState,
  selectedPrompt,
}: {
  item: CompanyListItem
  isSelected: boolean
  onToggle: () => void
  onScrape: () => void
  onClassify: () => void
  actionState: string
  analysisActionState: string
  selectedPrompt: PromptRead | null
}) {
  const scrapeBadge = scrapeBadgeForCompany(item)
  const isScraping = item.latest_scrape_terminal === false
  const isAnalysing = item.latest_analysis_terminal === false
  const canClassify = !!selectedPrompt?.enabled && item.latest_scrape_status === 'completed' && !isAnalysing

  return (
    <div className={`oc-company-card ${isSelected ? 'ring-1 ring-[var(--oc-accent)]' : ''}`}>
      <div className="flex items-start gap-2.5">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggle}
          className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-[var(--oc-border)] accent-[var(--oc-accent)]"
        />
        <div className="min-w-0 flex-1">
          <p
            className="truncate font-semibold text-[var(--oc-accent-ink)]"
            title={item.domain}
          >
            {item.domain}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {item.latest_decision ? (
              <span className={`oc-badge ${decisionBgClass(item.latest_decision)}`}>
                {item.latest_decision}
              </span>
            ) : (
              <Badge variant="neutral">No decision</Badge>
            )}
            <Badge variant={scrapeBadge.variant} title={scrapeBadge.title}>{scrapeBadge.label}</Badge>
            {(actionState || analysisActionState) && (
              <span className="text-[11px] text-[var(--oc-muted)]">{analysisActionState || actionState}</span>
            )}
          </div>
        </div>
      </div>
      <div className="mt-2.5 flex items-center gap-2">
        <Button
          variant="primary"
          size="xs"
          onClick={onScrape}
          disabled={isScraping}
        >
          <IconGlobe size={13} />
          {isScraping ? 'Scraping…' : 'Scrape'}
        </Button>
        <Button
          variant="secondary"
          size="xs"
          onClick={onClassify}
          disabled={!canClassify}
          title={!selectedPrompt?.enabled ? 'No enabled prompt' : item.latest_scrape_status !== 'completed' ? 'Scrape first' : undefined}
        >
          <IconZap size={13} />
          {isAnalysing ? 'Classifying…' : 'Classify'}
        </Button>
      </div>
    </div>
  )
}

// ── Main view ──────────────────────────────────────────────────────────────

export function CompaniesView({
  companies,
  isLoading,
  companyOffset,
  pageSize,
  decisionFilter,
  scrapeFilter,
  selectedCompanyIds,
  companyCounts,
  actionState,
  analysisActionState,
  isScrapingSelected,
  isScrapingAll,
  isClassifyingSelected,
  isClassifyingAll,
  isDeleting,
  isSelectingAll,
  isUploading,
  isDragActive,
  file,
  selectedPrompt,
  utilitiesOpen,
  onSetDecisionFilter,
  onSetScrapeFilter,
  onSetPageSize,
  onPagePrev,
  onPageNext,
  onToggleCompanySelection,
  onToggleVisibleSelection,
  onSelectAllFiltered,
  onClearSelection,
  onScrape,
  onScrapeSelected,
  onScrapeAll,
  onClassify,
  onClassifySelected,
  onClassifyAll,
  onDeleteSelected,
  onSetFile,
  onSetIsDragActive,
  onUpload,
  onToggleUtilities,
}: CompaniesViewProps) {
  // Derived state
  const effectiveTotal = companies?.total ?? companyCounts?.total ?? null
  const rangeLabel =
    companies && effectiveTotal !== null && effectiveTotal > 0
      ? `${Math.min(companies.offset + 1, effectiveTotal)}–${Math.min(companies.offset + companies.items.length, effectiveTotal)} of ${effectiveTotal.toLocaleString()}`
      : companies && companies.items.length > 0
        ? `${companies.offset + 1}–${companies.offset + companies.items.length}`
        : '0 of 0'
  const allVisibleSelected =
    companies ? companies.items.length > 0 && companies.items.every((c) => selectedCompanyIds.includes(c.id)) : false
  const canPagePrev = !!companies && companyOffset > 0 && !isLoading
  const canPageNext = !!companies && companies.has_more && !isLoading
  const canClassifyAll = !!selectedPrompt?.enabled && !isClassifyingAll

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="oc-toolbar space-y-3">
        {/* Top row: title + primary actions */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-bold tracking-tight md:text-lg">Companies</h2>
            <p className="hidden text-xs text-[var(--oc-muted)] sm:block">
              {rangeLabel} · {selectedCompanyIds.length > 0 ? `${selectedCompanyIds.length} selected` : 'none selected'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={onToggleUtilities}
            >
              <IconUpload size={15} />
              <span className="hidden sm:inline">{utilitiesOpen ? 'Hide ingest' : 'Ingest'}</span>
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={onScrapeAll}
              loading={isScrapingAll}
              disabled={isLoading}
            >
              <IconGlobe size={15} />
              <span className="hidden sm:inline">Scrape all</span>
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={onClassifyAll}
              loading={isClassifyingAll}
              disabled={!canClassifyAll}
              title={!selectedPrompt?.enabled ? 'Select an enabled prompt first' : undefined}
            >
              <IconZap size={15} />
              <span className="hidden sm:inline">Classify all</span>
            </Button>
          </div>
        </div>

        {/* Filters */}
        <FilterBar
          decisionFilter={decisionFilter}
          scrapeFilter={scrapeFilter}
          companyCounts={companyCounts}
          onSetDecisionFilter={onSetDecisionFilter}
          onSetScrapeFilter={onSetScrapeFilter}
        />

        {/* Pager */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs font-semibold text-(--oc-muted)">
              <input
                type="checkbox"
                checked={allVisibleSelected}
                onChange={onToggleVisibleSelection}
                className="h-4 w-4 rounded border-(--oc-border) accent-(--oc-accent)"
              />
              <span className="hidden sm:inline">Select page</span>
            </label>
            <button
              type="button"
              onClick={() => void onSelectAllFiltered()}
              disabled={isSelectingAll}
              className="rounded-lg border border-(--oc-border) bg-white px-2.5 py-1 text-xs font-bold text-(--oc-text) transition hover:border-(--oc-accent) hover:text-(--oc-accent-ink) disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSelectingAll ? 'Selecting…' : 'Select all matching'}
            </button>
          </div>
          <div className="ml-auto">
            <Pager
              rangeLabel={rangeLabel}
              canPrev={canPagePrev}
              canNext={canPageNext}
              onPrev={onPagePrev}
              onNext={onPageNext}
              pageSize={pageSize}
              onSetPageSize={onSetPageSize}
            />
          </div>
        </div>

        {/* Ingest panel */}
        {utilitiesOpen && (
          <IngestPanel
            file={file}
            isDragActive={isDragActive}
            isUploading={isUploading}
            onSetFile={onSetFile}
            onSetIsDragActive={onSetIsDragActive}
            onUpload={onUpload}
          />
        )}
      </div>

      {/* Content */}
      {isLoading && (!companies || companies.items.length === 0) ? (
        <SkeletonRows rows={8} />
      ) : !companies || companies.items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--oc-border)] py-16 text-center">
          <IconBuilding size={36} className="mb-3 text-[var(--oc-border)]" />
          <p className="font-semibold text-[var(--oc-accent-ink)]">No companies here</p>
          <p className="mt-1 text-sm text-[var(--oc-muted)]">
            {decisionFilter !== 'all' || scrapeFilter !== 'all'
              ? 'Try adjusting the filters above.'
              : 'Upload a CSV file to get started.'}
          </p>
        </div>
      ) : (
        <>
          {/* Mobile: card list */}
          <div className="space-y-2 md:hidden">
            {companies.items.map((item) => (
              <CompanyCard
                key={item.id}
                item={item}
                isSelected={selectedCompanyIds.includes(item.id)}
                onToggle={() => onToggleCompanySelection(item.id)}
                onScrape={() => onScrape(item)}
                onClassify={() => onClassify(item)}
                actionState={actionState[item.id] ?? ''}
                analysisActionState={analysisActionState[item.id] ?? ''}
                selectedPrompt={selectedPrompt}
              />
            ))}
          </div>

          {/* Desktop: table */}
          <div className="hidden md:block overflow-x-auto rounded-2xl border border-[var(--oc-border)] bg-white">
            <table className="oc-compact-table min-w-[880px]">
              <thead>
                <tr>
                  <th className="w-10">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={onToggleVisibleSelection}
                      className="h-4 w-4 rounded border-[var(--oc-border)] accent-[var(--oc-accent)]"
                    />
                  </th>
                  <th>Domain</th>
                  <th>Decision</th>
                  <th>Scrape</th>
                  <th className="w-[240px]">Actions</th>
                </tr>
              </thead>
              <tbody>
                {companies.items.map((item) => {
                  const scrapeBadge = scrapeBadgeForCompany(item)
                  const isScraping = item.latest_scrape_terminal === false
                  const isAnalysing = item.latest_analysis_terminal === false
                  const canClassify = !!selectedPrompt?.enabled && item.latest_scrape_status === 'completed' && !isAnalysing

                  return (
                    <tr key={item.id}>
                      <td className="w-10">
                        <input
                          type="checkbox"
                          checked={selectedCompanyIds.includes(item.id)}
                          onChange={() => onToggleCompanySelection(item.id)}
                          className="h-4 w-4 rounded border-[var(--oc-border)] accent-[var(--oc-accent)]"
                        />
                      </td>
                      <td title={`${item.domain}\n${item.raw_url}\n${item.normalized_url}`}>
                        <span className="block max-w-[360px] overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[var(--oc-accent-ink)]">
                          {item.domain}
                        </span>
                      </td>
                      <td>
                        {item.latest_decision ? (
                          <span className={`oc-badge ${decisionBgClass(item.latest_decision)}`}>
                            {item.latest_decision}
                          </span>
                        ) : (
                          <Badge variant="neutral">No decision</Badge>
                        )}
                      </td>
                      <td title={scrapeBadge.title}>
                        <Badge variant={scrapeBadge.variant}>{scrapeBadge.label}</Badge>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="primary"
                            size="xs"
                            onClick={() => onScrape(item)}
                            disabled={isScraping}
                          >
                            Scrape
                          </Button>
                          <Button
                            variant="secondary"
                            size="xs"
                            onClick={() => onClassify(item)}
                            disabled={!canClassify}
                          >
                            {isAnalysing ? 'Classifying…' : 'Classify'}
                          </Button>
                          <span className="text-[11px] text-[var(--oc-muted)]">
                            {analysisActionState[item.id] || actionState[item.id] || ''}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Bottom pager */}
          <div className="flex justify-end">
            <Pager
              rangeLabel={rangeLabel}
              canPrev={canPagePrev}
              canNext={canPageNext}
              onPrev={onPagePrev}
              onNext={onPageNext}
              pageSize={pageSize}
              onSetPageSize={onSetPageSize}
            />
          </div>
        </>
      )}

      {/* Floating bulk action bar */}
      <BulkActionBar
        selectedCount={selectedCompanyIds.length}
        onClearSelection={onClearSelection}
        onScrapeSelected={onScrapeSelected}
        onClassifySelected={onClassifySelected}
        onDeleteSelected={onDeleteSelected}
        onSelectAllFiltered={onSelectAllFiltered}
        isScrapingSelected={isScrapingSelected}
        isClassifyingSelected={isClassifyingSelected}
        isDeleting={isDeleting}
        isSelectingAll={isSelectingAll}
        selectedPrompt={selectedPrompt}
      />
    </div>
  )
}

// ── Missing import fix ─────────────────────────────────────────────────────
function IconBuilding({ size = 20, className = '' }: { size?: number; className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect x="2" y="3" width="16" height="14" rx="1.5" />
      <path d="M6 7h2M6 10h2M12 7h2M12 10h2M8 17v-4h4v4" />
    </svg>
  )
}
