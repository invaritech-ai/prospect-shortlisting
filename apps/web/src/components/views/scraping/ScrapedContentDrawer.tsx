import { useState } from 'react'
import type { MockScrapeRow } from '../../../lib/useAppData'
import { Drawer } from '../../ui/Drawer'

const MOCK_PAGES: Record<string, { kind: string; title: string; content: string }[]> = {
  default: [
    {
      kind: 'home',
      title: 'Home',
      content: `# Welcome

This is the **homepage** content extracted from the company's website.

## What we do

We build enterprise software that helps teams manage their workflows more efficiently. Our platform integrates with over 200 tools and supports 50,000+ companies worldwide.

## Key features

- Real-time collaboration
- Advanced analytics dashboard
- SOC 2 Type II certified
- 99.99% uptime SLA
- 24/7 enterprise support

## Pricing

Starting at $15/user/month with annual plans available. Enterprise pricing on request.`,
    },
    {
      kind: 'about',
      title: 'About',
      content: `# About Us

Founded in 2019, we're a Series B company with $45M raised from Sequoia and a16z. Headquartered in San Francisco with offices in London and Singapore.

## Team

450 employees across engineering, sales, and operations.

## Mission

To make enterprise software that people actually enjoy using.`,
    },
    {
      kind: 'product',
      title: 'Product',
      content: `# Product Overview

Our platform consists of three core modules:

1. **Workflow Engine** — visual drag-and-drop process builder
2. **Analytics Suite** — real-time dashboards with 100+ pre-built templates
3. **Integration Hub** — 200+ native integrations, REST API, webhooks

### Supported Industries
- Financial Services
- Healthcare
- Manufacturing
- Retail & eCommerce`,
    },
  ],
}

interface ScrapedContentDrawerProps {
  row: MockScrapeRow | null
  onClose: () => void
}

export function ScrapedContentDrawer({ row, onClose }: ScrapedContentDrawerProps) {
  const [activeTab, setActiveTab] = useState('home')

  if (!row) return null

  const pages = MOCK_PAGES.default
  const activePage = pages.find((p) => p.kind === activeTab) ?? pages[0]

  return (
    <Drawer
      isOpen
      onClose={onClose}
      title={row.domain}
      subtitle={`S1 · ${row.pagesCount} pages scraped`}
      accentColor="var(--s1)"
      size="lg"
    >
      <div className="oc-drawer-tabs">
        {pages.map((p) => (
          <button key={p.kind} type="button" className="oc-drawer-tab"
            data-active={activeTab === p.kind ? 'true' : 'false'}
            onClick={() => setActiveTab(p.kind)}
          >{p.title}</button>
        ))}
      </div>

      <div className="oc-markdown" style={{ fontSize: '0.875rem', lineHeight: 1.7 }}>
        {activePage.content.split('\n').map((line, i) => {
          if (line.startsWith('## ')) return <h2 key={i} style={{ fontSize: '1rem', fontWeight: 700, marginTop: '1rem', marginBottom: '0.375rem' }}>{line.slice(3)}</h2>
          if (line.startsWith('# '))  return <h1 key={i} style={{ fontSize: '1.125rem', fontWeight: 700, marginTop: '0.5rem', marginBottom: '0.375rem', color: 'var(--oc-text)' }}>{line.slice(2)}</h1>
          if (line.startsWith('### ')) return <h3 key={i} style={{ fontSize: '0.9375rem', fontWeight: 600, marginTop: '0.75rem', marginBottom: '0.25rem' }}>{line.slice(4)}</h3>
          if (line.trim() === '') return <div key={i} style={{ height: '0.5rem' }} />
          if (line.startsWith('- ')) return <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.25rem' }}><span style={{ color: 'var(--s1)', fontWeight: 700 }}>·</span><span>{line.slice(2)}</span></div>
          if (/^\d+\./.test(line)) {
            const [num, ...rest] = line.split('. ')
            return (
              <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--s1)', fontWeight: 700, minWidth: '1.25rem' }}>{num}.</span>
                <span>{rest.join('. ').replace(/\*\*(.*?)\*\*/g, '$1')}</span>
              </div>
            )
          }
          return <p key={i} style={{ margin: '0 0 0.25rem' }}>{line.replace(/\*\*(.*?)\*\*/g, '$1')}</p>
        })}
      </div>
    </Drawer>
  )
}
