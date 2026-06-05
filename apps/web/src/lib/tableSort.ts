export type SortDir = 'asc' | 'desc'

export type TableSortState = {
  sortBy: string
  sortDir: SortDir
}

export function nextTableSort(
  current: TableSortState,
  field: string,
  defaultDir: SortDir,
): TableSortState {
  if (current.sortBy === field) {
    return { sortBy: field, sortDir: current.sortDir === 'asc' ? 'desc' : 'asc' }
  }
  return { sortBy: field, sortDir: defaultDir }
}
