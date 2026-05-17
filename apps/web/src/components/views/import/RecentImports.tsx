import type { UploadRead } from '../../../lib/types'
import type { CampaignRead } from '../../../lib/types'

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins  = Math.floor(diff / 60_000)
  const hours = Math.floor(diff / 3_600_000)
  const days  = Math.floor(diff / 86_400_000)
  if (mins < 1)   return 'just now'
  if (mins < 60)  return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

interface RecentImportsProps {
  uploads: UploadRead[]
  campaigns: CampaignRead[]
}

export function RecentImports({ uploads, campaigns }: RecentImportsProps) {
  if (uploads.length === 0) return null

  const campaignName = (id: string | null) =>
    id ? (campaigns.find((c) => c.id === id)?.name ?? 'Unknown campaign') : '—'

  return (
    <section>
      <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Recent Imports</p>

      {/* Desktop table */}
      <div className="hidden md:block" style={{ borderRadius: '0.875rem', border: '1px solid var(--oc-border)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--oc-surface-dim)', borderBottom: '1px solid var(--oc-border)' }}>
              {['File', 'Campaign', 'Rows', 'Issues', 'Uploaded'].map((h) => (
                <th key={h} style={{ padding: '0.625rem 0.875rem', textAlign: 'left', fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.14em', color: 'var(--oc-muted)' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {uploads.map((u) => (
              <tr key={u.id} style={{ borderTop: '1px solid color-mix(in srgb, var(--oc-border) 70%, transparent)', transition: 'background 120ms' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--oc-surface-dim)' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = '' }}
              >
                <td style={{ padding: '0.75rem 0.875rem', fontSize: '0.9375rem', color: 'var(--oc-text)', fontWeight: 500, maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {u.filename}
                </td>
                <td style={{ padding: '0.75rem 0.875rem', fontSize: '0.875rem', color: 'var(--oc-muted)', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {campaignName(u.campaign_id)}
                </td>
                <td style={{ padding: '0.75rem 0.875rem', fontFamily: 'var(--font-mono)', fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)' }}>
                  {u.valid_count.toLocaleString()}
                </td>
                <td style={{ padding: '0.75rem 0.875rem' }}>
                  {u.invalid_count > 0 ? (
                    <span className="oc-badge oc-badge-warn">{u.invalid_count} skipped</span>
                  ) : (
                    <span className="oc-badge oc-badge-success">Clean</span>
                  )}
                </td>
                <td style={{ padding: '0.75rem 0.875rem', fontSize: '0.875rem', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                  {relativeTime(u.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {uploads.map((u) => (
          <div key={u.id} style={{ borderRadius: '0.875rem', border: '1px solid var(--oc-border)', background: 'var(--oc-surface)', padding: '0.875rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--oc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                {u.filename}
              </span>
              {u.invalid_count > 0
                ? <span className="oc-badge oc-badge-warn" style={{ flexShrink: 0 }}>{u.invalid_count} skipped</span>
                : <span className="oc-badge oc-badge-success" style={{ flexShrink: 0 }}>Clean</span>
              }
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', fontWeight: 600, color: 'var(--oc-text)' }}>
                {u.valid_count.toLocaleString()} rows
              </span>
              <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)' }}>
                {campaignName(u.campaign_id)}
              </span>
              <span style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', marginLeft: 'auto' }}>
                {relativeTime(u.created_at)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
