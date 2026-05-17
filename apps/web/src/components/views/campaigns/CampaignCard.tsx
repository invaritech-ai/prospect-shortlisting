import type { CampaignRead } from '../../../lib/types'
import type { CampaignPipelineSummary } from '../../../lib/mockData'
import { CampaignMiniProgress } from './CampaignMiniProgress'

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

interface CampaignCardProps {
  campaign: CampaignRead
  summary: CampaignPipelineSummary
  isActive: boolean
  onOpen: () => void
  onEdit: () => void
  onDelete: () => void
}

export function CampaignCard({ campaign, summary, isActive, onOpen, onEdit, onDelete }: CampaignCardProps) {
  return (
    <div
      className="oc-panel"
      style={{
        padding: '1.375rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        cursor: 'default',
        borderColor: isActive ? 'var(--oc-accent)' : undefined,
        boxShadow: isActive ? '0 0 0 2px color-mix(in srgb, var(--oc-accent) 20%, transparent)' : undefined,
        transition: 'box-shadow 160ms, border-color 160ms',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem' }}>
        <div style={{ minWidth: 0 }}>
          {isActive && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
              fontSize: '0.5625rem', fontWeight: 700, textTransform: 'uppercase',
              letterSpacing: '0.14em', color: 'var(--oc-accent)',
              marginBottom: '0.3rem',
            }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '9999px', backgroundColor: 'var(--oc-accent)', display: 'inline-block' }} />
              Active
            </span>
          )}
          <h2 style={{
            fontFamily: 'var(--font-display)', fontSize: '1.125rem',
            color: 'var(--oc-text)', margin: 0, lineHeight: 1.2,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {campaign.name}
          </h2>
          {campaign.description && (
            <p style={{ fontSize: '0.8125rem', color: 'var(--oc-muted)', margin: '0.25rem 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {campaign.description}
            </p>
          )}
        </div>

        {/* Actions menu */}
        <div style={{ display: 'flex', gap: '0.375rem', flexShrink: 0 }}>
          <button type="button" onClick={onEdit}
            style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--oc-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem 0.375rem', borderRadius: '0.375rem', fontFamily: 'inherit', transition: 'color 160ms, background 160ms' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--oc-text)'; e.currentTarget.style.background = 'var(--oc-surface-dim)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-muted)'; e.currentTarget.style.background = 'none' }}
          >
            Edit
          </button>
          <button type="button" onClick={onDelete}
            style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--oc-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem 0.375rem', borderRadius: '0.375rem', fontFamily: 'inherit', transition: 'color 160ms, background 160ms' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--oc-fail-text)'; e.currentTarget.style.background = 'var(--oc-fail-bg)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--oc-muted)'; e.currentTarget.style.background = 'none' }}
          >
            Delete
          </button>
        </div>
      </div>

      {/* Company count */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.375rem' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums', color: 'var(--oc-text)', lineHeight: 1 }}>
          {summary.total.toLocaleString()}
        </span>
        <span style={{ fontSize: '0.875rem', color: 'var(--oc-muted)', fontWeight: 500 }}>companies</span>
      </div>

      {/* Mini pipeline progress */}
      <CampaignMiniProgress summary={summary} />

      {/* Footer */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 'auto', paddingTop: '0.25rem' }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
          Active {relativeTime(summary.lastActivity)}
        </span>
        <button type="button" onClick={onOpen} className="oc-btn oc-btn-primary oc-btn-sm">
          {isActive ? 'View pipeline →' : 'Open campaign →'}
        </button>
      </div>
    </div>
  )
}
