import { useCallback, useEffect, useRef, useState } from 'react'
import type { DragEvent, FormEvent } from 'react'
import {
  ApiError,
  createScrapeJob,
  deleteCompanies,
  enqueueRunAll,
  getCompaniesExportUrl,
  listCompanies,
  uploadFile,
} from './lib/api'
import type { CompanyList, CompanyListItem, DecisionFilter } from './lib/types'

const DEFAULT_COMPANY_PAGE_SIZE = 100
const PAGE_SIZE_OPTIONS = [50, 100, 200] as const
const DECISION_FILTERS: Array<{ value: DecisionFilter; label: string }> = [
  { value: 'all', label: 'All (ordered)' },
  { value: 'unlabeled', label: 'No label' },
  { value: 'possible', label: 'Possible' },
  { value: 'unknown', label: 'Unknown' },
  { value: 'crap', label: 'Crap' },
]

function App() {
  const companyCacheRef = useRef<Record<string, CompanyList>>({})
  const [file, setFile] = useState<File | null>(null)
  const [companies, setCompanies] = useState<CompanyList | null>(null)
  const [companyOffset, setCompanyOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_COMPANY_PAGE_SIZE)
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>('all')
  const [isCompaniesLoading, setIsCompaniesLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isDragActive, setIsDragActive] = useState(false)
  const [actionState, setActionState] = useState<Record<string, string>>({})
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<string[]>([])
  const [error, setError] = useState('')

  const parseError = (err: unknown): string => {
    if (err instanceof ApiError) {
      if (typeof err.detail === 'string') {
        return err.detail
      }
      if (Array.isArray(err.detail)) {
        return JSON.stringify(err.detail)
      }
      return JSON.stringify(err.detail)
    }
    if (err instanceof Error) {
      return err.message
    }
    return 'Unknown error'
  }

  const cacheKeyFor = useCallback(
    (offset: number, limit: number, nextDecisionFilter: DecisionFilter): string =>
      `${nextDecisionFilter}:${limit}:${offset}`,
    [],
  )

  const prefetchCompanies = useCallback(
    async (offset: number, limit: number, nextDecisionFilter: DecisionFilter) => {
      const key = cacheKeyFor(offset, limit, nextDecisionFilter)
      if (companyCacheRef.current[key]) {
        return
      }
      try {
        const response = await listCompanies(limit, offset, nextDecisionFilter)
        companyCacheRef.current[key] = response
      } catch {
        // Prefetch should never interrupt operator flow.
      }
    },
    [cacheKeyFor],
  )

  const loadCompanies = useCallback(
    async (
      offset = 0,
      nextLimit = pageSize,
      nextDecisionFilter: DecisionFilter = decisionFilter,
    ) => {
      const key = cacheKeyFor(offset, nextLimit, nextDecisionFilter)
      const cached = companyCacheRef.current[key]
      if (cached) {
        setCompanies(cached)
        setCompanyOffset(offset)
        setSelectedCompanyIds([])
        void prefetchCompanies(offset + nextLimit, nextLimit, nextDecisionFilter)
        return
      }

      setIsCompaniesLoading(true)
      try {
        const response = await listCompanies(nextLimit, offset, nextDecisionFilter)
        companyCacheRef.current[key] = response
        setCompanies(response)
        setCompanyOffset(offset)
        setSelectedCompanyIds([])
        if (response.has_more) {
          void prefetchCompanies(offset + nextLimit, nextLimit, nextDecisionFilter)
        }
      } catch (err) {
        setError(parseError(err))
      } finally {
        setIsCompaniesLoading(false)
      }
    },
    [cacheKeyFor, decisionFilter, pageSize, prefetchCompanies],
  )

  useEffect(() => {
    void loadCompanies(0, pageSize, decisionFilter)
  }, [decisionFilter, loadCompanies, pageSize])

  const onUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!file) {
      setError('Choose a file first.')
      return
    }
    setError('')
    setIsUploading(true)
    try {
      await uploadFile(file)
      companyCacheRef.current = {}
      setFile(null)
      await loadCompanies(0, pageSize, decisionFilter)
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsUploading(false)
    }
  }

  const onDragOver = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setIsDragActive(true)
  }

  const onDragLeave = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setIsDragActive(false)
  }

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setIsDragActive(false)
    const droppedFile = event.dataTransfer.files?.[0]
    if (!droppedFile) {
      return
    }
    setFile(droppedFile)
    setError('')
  }

  const onScrape = async (company: CompanyListItem) => {
    setError('')
    setActionState((current) => ({ ...current, [company.id]: 'Creating scrape job...' }))
    try {
      const job = await createScrapeJob({ website_url: company.normalized_url })
      await enqueueRunAll(job.id)
      setActionState((current) => ({ ...current, [company.id]: 'Queued' }))
    } catch (err) {
      setActionState((current) => ({ ...current, [company.id]: 'Failed' }))
      setError(parseError(err))
    }
  }

  const toggleCompanySelection = (companyId: string) => {
    setSelectedCompanyIds((current) =>
      current.includes(companyId) ? current.filter((item) => item !== companyId) : [...current, companyId],
    )
  }

  const toggleVisibleSelection = () => {
    if (!companies) {
      return
    }
    const visibleIds = companies.items.map((item) => item.id)
    const allVisibleSelected = visibleIds.every((id) => selectedCompanyIds.includes(id))
    setSelectedCompanyIds((current) => {
      if (allVisibleSelected) {
        return current.filter((id) => !visibleIds.includes(id))
      }
      return Array.from(new Set([...current, ...visibleIds]))
    })
  }

  const onDeleteSelected = async () => {
    if (selectedCompanyIds.length === 0) {
      return
    }
    const confirmed = window.confirm(
      `Permanently delete ${selectedCompanyIds.length} compan${selectedCompanyIds.length === 1 ? 'y' : 'ies'}? This cannot be undone.`,
    )
    if (!confirmed) {
      return
    }

    setError('')
    setIsDeleting(true)
    try {
      await deleteCompanies(selectedCompanyIds)
      companyCacheRef.current = {}
      const currentLimit = companies?.limit ?? pageSize
      const nextOffset =
        companies && companies.items.length === selectedCompanyIds.length && companyOffset > 0
          ? Math.max(companyOffset - currentLimit, 0)
          : companyOffset
      await loadCompanies(nextOffset, pageSize, decisionFilter)
    } catch (err) {
      setError(parseError(err))
    } finally {
      setIsDeleting(false)
    }
  }

  const rangeLabel =
    companies && companies.total !== null && companies.total > 0
      ? `${Math.min(companies.offset + 1, companies.total)}-${Math.min(companies.offset + companies.items.length, companies.total)} of ${companies.total}`
      : companies && companies.items.length > 0
        ? `${companies.offset + 1}-${companies.offset + companies.items.length}`
      : '0 of 0'
  const allVisibleSelected =
    companies ? companies.items.length > 0 && companies.items.every((item) => selectedCompanyIds.includes(item.id)) : false
  const canPagePrev = !!companies && companyOffset > 0 && !isCompaniesLoading
  const canPageNext = !!companies && companies.has_more && !isCompaniesLoading

  const decisionBadgeClass = (decision: string | null): string => {
    if (!decision) {
      return 'bg-slate-100 text-slate-600'
    }
    const token = decision.trim().toLowerCase()
    if (token === 'possible') {
      return 'bg-emerald-50 text-emerald-800'
    }
    if (token === 'unknown') {
      return 'bg-amber-50 text-amber-800'
    }
    if (token === 'crap') {
      return 'bg-rose-50 text-rose-800'
    }
    return 'bg-indigo-50 text-indigo-800'
  }

  const renderPager = () => (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() =>
          void loadCompanies(Math.max(companyOffset - (companies?.limit ?? pageSize), 0), pageSize, decisionFilter)
        }
        disabled={!canPagePrev}
        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        Prev
      </button>
      <button
        type="button"
        onClick={() => void loadCompanies(companyOffset + (companies?.limit ?? pageSize), pageSize, decisionFilter)}
        disabled={!canPageNext}
        className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        Next
      </button>
      <span className="oc-kbd">{rangeLabel}</span>
    </div>
  )

  return (
    <div className="oc-shell">
      <main className="oc-main space-y-6">
        <header className="oc-panel p-5 md:p-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="oc-kbd mb-2">Prospect Pipeline</p>
              <h1 className="text-3xl font-extrabold tracking-tight text-[var(--oc-text)] md:text-4xl">
                Companies Queue
              </h1>
              <p className="mt-2 max-w-3xl text-sm text-[var(--oc-muted)] md:text-base">
                Start from the company list. Review uploaded domains, see decisions if they exist, and trigger scrape
                work directly from the operator table.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)] px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--oc-muted)]">API</p>
                  <p className="mt-1 font-semibold text-[var(--oc-accent-ink)]">{import.meta.env.VITE_API_BASE_URL}</p>
                </div>
                <a
                  href={getCompaniesExportUrl()}
                  className="rounded-lg border border-[var(--oc-border)] bg-white px-3 py-2 text-xs font-bold text-[var(--oc-text)] transition hover:border-[var(--oc-accent)] hover:text-[var(--oc-accent-ink)]"
                >
                  Export CSV
                </a>
              </div>
            </div>
          </div>
        </header>

        <section className="grid gap-6 lg:grid-cols-7">
          <article className="oc-panel p-5 lg:col-span-5 md:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold tracking-tight">All Companies</h2>
                <p className="mt-1 text-sm text-[var(--oc-muted)]">
                  Ordered by default as: no label, then Possible, then Unknown, then Crap.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => void onDeleteSelected()}
                  disabled={selectedCompanyIds.length === 0 || isDeleting}
                  className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isDeleting ? 'Deleting...' : `Delete selected (${selectedCompanyIds.length})`}
                </button>
                <label className="text-xs font-semibold text-[var(--oc-muted)]">
                  Rows
                  <select
                    value={pageSize}
                    onChange={(event) => setPageSize(Number(event.target.value))}
                    className="ml-2 rounded-lg border border-[var(--oc-border)] bg-white px-2 py-1 text-xs font-semibold text-[var(--oc-text)]"
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
                {renderPager()}
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              {DECISION_FILTERS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setDecisionFilter(item.value)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold transition ${
                    decisionFilter === item.value
                      ? 'bg-[var(--oc-accent)] text-white'
                      : 'border border-[var(--oc-border)] bg-white text-[var(--oc-muted)] hover:text-[var(--oc-text)]'
                  }`}
                >
                  {item.label}
                </button>
              ))}
              <span className="text-xs text-[var(--oc-muted)]">Select visible rows, then bulk delete.</span>
            </div>

            <div className="mt-4 overflow-x-auto">
              {isCompaniesLoading ? (
                <p className="py-6 text-sm text-[var(--oc-muted)]">Loading companies...</p>
              ) : !companies || companies.items.length === 0 ? (
                <p className="py-6 text-sm text-[var(--oc-muted)]">No companies in this view.</p>
              ) : (
                <>
                  <table className="w-full min-w-[1120px] border-collapse">
                    <thead>
                      <tr className="bg-white text-left text-[11px] uppercase tracking-[0.14em] text-[var(--oc-muted)]">
                        <th className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={allVisibleSelected}
                            onChange={toggleVisibleSelection}
                            className="h-4 w-4 rounded border-[var(--oc-border)]"
                          />
                        </th>
                        <th className="px-3 py-2">Domain</th>
                        <th className="px-3 py-2">URL</th>
                        <th className="px-3 py-2">Decision</th>
                        <th className="px-3 py-2">Added</th>
                        <th className="px-3 py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {companies.items.map((item) => (
                        <tr key={item.id} className="border-t border-[var(--oc-border)] align-top text-xs">
                          <td className="px-3 py-2">
                            <input
                              type="checkbox"
                              checked={selectedCompanyIds.includes(item.id)}
                              onChange={() => toggleCompanySelection(item.id)}
                              className="h-4 w-4 rounded border-[var(--oc-border)]"
                            />
                          </td>
                          <td className="px-3 py-2">
                            <p className="font-semibold text-[var(--oc-accent-ink)]">{item.domain}</p>
                            <p className="mt-0.5 font-mono text-[11px] text-[var(--oc-muted)]">{item.raw_url}</p>
                          </td>
                          <td className="px-3 py-2 font-mono text-[11px] text-[var(--oc-muted)]">{item.normalized_url}</td>
                          <td className="px-3 py-2">
                            {item.latest_decision ? (
                              <div>
                                <span className={`rounded-md px-2 py-1 text-[11px] font-bold ${decisionBadgeClass(item.latest_decision)}`}>
                                  {item.latest_decision}
                                </span>
                                <p className="mt-0.5 text-[11px] text-[var(--oc-muted)]">
                                  confidence {item.latest_confidence ?? '-'}
                                </p>
                              </div>
                            ) : (
                              <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">
                                No decision
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-xs text-[var(--oc-muted)]">
                            {new Date(item.created_at).toLocaleString()}
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex flex-col gap-1.5">
                              <button
                                type="button"
                                onClick={() => void onScrape(item)}
                                className="rounded-lg bg-[var(--oc-accent)] px-3 py-1.5 text-xs font-bold text-white transition hover:brightness-95"
                              >
                                Scrape
                              </button>
                              <button
                                type="button"
                                disabled
                                className="rounded-lg border border-[var(--oc-border)] px-3 py-1.5 text-xs font-bold text-[var(--oc-muted)] opacity-60"
                              >
                                Classify
                              </button>
                              <p className="text-[11px] text-[var(--oc-muted)]">{actionState[item.id] ?? ''}</p>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="mt-3 flex justify-end">{renderPager()}</div>
                </>
              )}
            </div>
          </article>

          <form onSubmit={onUpload} className="oc-panel space-y-4 p-5 lg:col-span-2 md:p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold tracking-tight">Ingest File</h2>
              <span className="oc-kbd">secondary</span>
            </div>
            <p className="text-sm text-[var(--oc-muted)]">
              Upload remains available, but it is no longer the primary operator workflow.
            </p>
            <label
              htmlFor="upload-file"
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              className={`block cursor-pointer rounded-xl border-2 border-dashed px-4 py-8 transition ${
                isDragActive
                  ? 'border-[var(--oc-accent)] bg-white shadow-[0_0_0_4px_rgba(15,118,110,0.08)]'
                  : 'border-[var(--oc-border)] bg-[var(--oc-surface)] hover:border-[var(--oc-accent)]'
              }`}
            >
              <input
                id="upload-file"
                type="file"
                accept=".csv,.txt,.xls,.xlsx"
                className="hidden"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <p className="text-center text-sm font-semibold text-[var(--oc-accent-ink)]">
                {file ? file.name : isDragActive ? 'Drop file here' : 'Choose a file to upload'}
              </p>
              <p className="mt-1 text-center text-xs text-[var(--oc-muted)]">
                Drag and drop or click. Refreshes the company table after parse completes.
              </p>
            </label>
            <button
              type="submit"
              disabled={!file || isUploading}
              className="inline-flex w-full items-center justify-center rounded-xl bg-[var(--oc-accent)] px-4 py-3 text-sm font-bold text-white transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isUploading ? 'Uploading...' : 'Upload and Parse'}
            </button>
          </form>
        </section>

        {error && (
          <section className="oc-panel border-[var(--oc-danger-bg)] bg-[var(--oc-danger-bg)] p-4">
            <p className="font-medium text-[var(--oc-danger-text)]">{error}</p>
          </section>
        )}
      </main>
    </div>
  )
}

export default App
