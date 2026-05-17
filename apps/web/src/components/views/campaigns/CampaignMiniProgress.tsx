import type { CampaignPipelineSummary } from '../../../lib/mockData'

interface CampaignMiniProgressProps {
  summary: CampaignPipelineSummary
}

export function CampaignMiniProgress({ summary }: CampaignMiniProgressProps) {
  const { total, notScraped, scraped, classified, possible, validEmails } = summary
  if (total === 0) return null

  // Each slice is a count of companies AT that stage right now
  const segments = [
    { label: 'Not scraped', count: notScraped,  color: 'var(--oc-border)' },
    { label: 'Scraping',    count: scraped,      color: 'var(--s1)' },
    { label: 'Reviewed',    count: classified,   color: 'var(--s2)' },
    { label: 'Possible',    count: possible,     color: 'var(--s3)' },
    { label: 'Validated',   count: validEmails,  color: 'var(--s5)' },
  ].filter((s) => s.count > 0)

  return (
    <div>
      {/* Segmented bar */}
      <div style={{ display: 'flex', height: '0.3125rem', borderRadius: '9999px', overflow: 'hidden', background: 'var(--oc-border)', gap: '1px' }}>
        {segments.map((seg) => (
          <div
            key={seg.label}
            title={`${seg.label}: ${seg.count.toLocaleString()}`}
            style={{
              height: '100%',
              width: `${(seg.count / total) * 100}%`,
              backgroundColor: seg.color,
              transition: 'width 400ms ease',
              minWidth: seg.count > 0 ? '3px' : 0,
            }}
          />
        ))}
      </div>

      {/* Key stats row */}
      <div style={{ display: 'flex', gap: '1rem', marginTop: '0.625rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--s2)' }}>{possible.toLocaleString()}</span>
          {' '}possible
        </span>
        <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--s5)' }}>{validEmails.toLocaleString()}</span>
          {' '}valid emails
        </span>
        {notScraped > 0 && (
          <span style={{ fontSize: '0.75rem', color: 'var(--oc-muted)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--oc-muted)' }}>{notScraped.toLocaleString()}</span>
            {' '}pending
          </span>
        )}
      </div>
    </div>
  )
}
