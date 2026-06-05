import type { EmailVerificationContactRow } from '../../../lib/types'
import { SortableHeader } from '../../ui/SortableHeader'
import { ValidationStatusBadge } from './ValidationStatusBadge'

function contactName(row: EmailVerificationContactRow): string {
  return `${row.first_name} ${row.last_name}`.trim() || 'Unknown contact'
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

interface ValidationTableProps {
  rows: EmailVerificationContactRow[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onValidate: (id: string) => void
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (field: string) => void
  validateDisabled?: boolean
}

export function ValidationTable({
  rows,
  selected,
  onToggleSelect,
  onToggleSelectAll,
  onValidate,
  sortBy,
  sortDir,
  onSort,
  validateDisabled = false,
}: ValidationTableProps) {
  const allSelected = rows.length > 0 && rows.every((row) => selected.has(row.contact_id))

  return (
    <div className="oc-panel" style={{ overflow: 'hidden', padding: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="oc-compact-table" style={{ minWidth: '860px' }}>
          <thead>
            <tr>
              <th style={{ width: '2.5rem', paddingLeft: '1rem' }}>
                <input type="checkbox" checked={allSelected} onChange={onToggleSelectAll} style={{ accentColor: 'var(--s5)' }} />
              </th>
              <SortableHeader label="Contact" field="contact" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Company" field="company" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Email" field="email" sortBy={sortBy} sortDir={sortDir} onSort={onSort} />
              <SortableHeader label="Status" field="status" sortBy={sortBy} sortDir={sortDir} onSort={onSort} style={{ width: '150px' }} />
              <SortableHeader label="Verified" field="verified" sortBy={sortBy} sortDir={sortDir} onSort={onSort} style={{ width: '120px' }} />
              <th style={{ width: '120px' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isSelected = selected.has(row.contact_id)
              return (
                <tr key={row.contact_id} style={{ backgroundColor: isSelected ? 'color-mix(in srgb, var(--s5) 5%, transparent)' : undefined }}>
                  <td style={{ paddingLeft: '1rem' }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleSelect(row.contact_id)}
                      style={{ accentColor: 'var(--s5)' }}
                    />
                  </td>
                  <td>
                    <div style={{ fontWeight: 650, fontSize: '0.875rem', color: 'var(--oc-text)' }}>{contactName(row)}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--oc-muted)', marginTop: '0.0625rem' }}>
                      {row.title || 'No title'}
                    </div>
                  </td>
                  <td>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', color: 'var(--oc-text)' }}>{row.domain}</span>
                  </td>
                  <td>
                    <a
                      href={`mailto:${row.selected_email}`}
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.8125rem',
                        fontWeight: 550,
                        color: 'var(--oc-text)',
                        textDecoration: 'none',
                        borderBottom: '1px dashed var(--oc-border)',
                      }}
                    >
                      {row.selected_email}
                    </a>
                  </td>
                  <td><ValidationStatusBadge status={row.status} /></td>
                  <td style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {formatDate(row.verified_at)}
                  </td>
                  <td>
                    {row.action_label && (
                      <button
                        type="button"
                        onClick={() => onValidate(row.contact_id)}
                        disabled={validateDisabled}
                        className="oc-btn oc-btn-secondary oc-btn-sm"
                        style={{ opacity: validateDisabled ? 0.45 : 1 }}
                      >
                        {row.action_label}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
