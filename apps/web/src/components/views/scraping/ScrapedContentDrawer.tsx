import { useState, useEffect } from 'react'
import type { DomainRead, ScrapeResultRead } from '../../../lib/types'
import { getScrapeResult } from '../../../lib/api'
import { Drawer } from '../../ui/Drawer'

const PAGE_KIND_LABELS: Record<string, string> = {
  home: 'Home',
  about: 'About',
  products: 'Products',
  services: 'Services',
  pricing: 'Pricing',
  contact: 'Contact',
  team: 'Team',
  leadership: 'Leadership',
}

function renderMarkdown(text: string) {
  return text.split('\n').map((line, i) => {
    if (line.startsWith('### ')) return <h3 key={i} style={{ fontSize: '0.9375rem', fontWeight: 600, marginTop: '0.75rem', marginBottom: '0.25rem' }}>{line.slice(4)}</h3>
    if (line.startsWith('## '))  return <h2 key={i} style={{ fontSize: '1rem', fontWeight: 700, marginTop: '1rem', marginBottom: '0.375rem' }}>{line.slice(3)}</h2>
    if (line.startsWith('# '))  return <h1 key={i} style={{ fontSize: '1.125rem', fontWeight: 700, marginTop: '0.5rem', marginBottom: '0.375rem', color: 'var(--oc-text)' }}>{line.slice(2)}</h1>
    if (line.trim() === '') return <div key={i} style={{ height: '0.5rem' }} />
    if (line.startsWith('- ')) return (
      <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.25rem' }}>
        <span style={{ color: 'var(--s1)', fontWeight: 700 }}>·</span>
        <span>{line.slice(2).replace(/\*\*(.*?)\*\*/g, '$1')}</span>
      </div>
    )
    return <p key={i} style={{ margin: '0 0 0.25rem' }}>{line.replace(/\*\*(.*?)\*\*/g, '$1')}</p>
  })
}

interface ScrapedContentDrawerProps {
  domain: DomainRead | null
  onClose: () => void
}

export function ScrapedContentDrawer({ domain, onClose }: ScrapedContentDrawerProps) {
  const [result, setResult] = useState<ScrapeResultRead | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('home')

  useEffect(() => {
    if (!domain) { setResult(null); return }
    // Load the scrape result for this domain
    setLoading(true)
    setResult(null)
    getScrapeResult(domain.id, domain.campaign_id)
      .then((data) => data as ScrapeResultRead | null)
      .then((data) => { setResult(data); setActiveTab('home') })
      .catch(() => setResult(null))
      .finally(() => setLoading(false))
  }, [domain])

  if (!domain) return null

  const successPages = (result?.scraped_pages_json ?? []).filter((p) => p.success && p.markdown)

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title={domain.domain}
      subtitle={`S1 · ${successPages.length} pages scraped`}
      accentColor="var(--s1)"
      size="lg"
    >
      {loading && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--oc-muted)' }}>Loading…</div>
      )}

      {!loading && result && successPages.length === 0 && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--oc-muted)' }}>
          {result.error_code
            ? `Scrape failed: ${result.error_code}`
            : 'No content was scraped for this domain.'}
        </div>
      )}

      {!loading && successPages.length > 0 && (
        <>
          <div className="oc-drawer-tabs">
            {successPages.map((p) => (
              <button
                key={p.kind}
                type="button"
                className="oc-drawer-tab"
                data-active={activeTab === p.kind ? 'true' : 'false'}
                onClick={() => setActiveTab(p.kind)}
              >
                {PAGE_KIND_LABELS[p.kind] ?? p.kind}
              </button>
            ))}
          </div>

          {successPages.filter((p) => p.kind === activeTab).map((p) => (
            <div key={p.kind} className="oc-markdown" style={{ fontSize: '0.875rem', lineHeight: 1.7 }}>
              {renderMarkdown(p.markdown ?? '')}
            </div>
          ))}
        </>
      )}

      {!loading && !result && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--oc-muted)' }}>
          Could not load scrape results.
        </div>
      )}
    </Drawer>
  )
}
