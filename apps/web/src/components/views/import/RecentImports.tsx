import type { UploadRead, CampaignRead } from '../../../lib/types'

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

  const campaignName = (id: string) =>
    campaigns.find((c) => c.id === id)?.name ?? 'Unknown campaign'

  return (
    <section>
      <p className="oc-label" style={{ marginBottom: '0.75rem' }}>Recent uploads</p>

      <div className="oc-panel" style={{ overflow: 'hidden', padding: 0 }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="oc-compact-table" style={{ minWidth: '480px' }}>
            <thead>
              <tr>
                <th>File</th>
                <th>Campaign</th>
                <th style={{ width: '80px', textAlign: 'right' }}>Rows</th>
                <th style={{ width: '100px', textAlign: 'right' }}>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {uploads.map((u) => (
                <tr key={u.id}>
                  <td style={{ maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }}>
                    {u.filename}
                  </td>
                  <td style={{ color: 'var(--oc-muted)', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {campaignName(u.campaign_id)}
                  </td>
                  <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                    {u.row_count.toLocaleString()}
                  </td>
                  <td style={{ textAlign: 'right', color: 'var(--oc-muted)', whiteSpace: 'nowrap' }}>
                    {relativeTime(u.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
