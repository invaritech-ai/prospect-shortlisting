import { useEffect, useRef, useState } from 'react'
import type { CampaignRead } from '../../../lib/types'

interface CampaignPickerProps {
  campaigns: CampaignRead[]
  selectedId: string | null
  onSelect: (id: string) => void
  onManage: () => void
  collapsed: boolean
}

export function CampaignPicker({ campaigns, selectedId, onSelect, onManage, collapsed }: CampaignPickerProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const active = campaigns.find((c) => c.id === selectedId) ?? null

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} style={{ position: 'relative', padding: collapsed ? '0 0.5rem' : '0 0.75rem', marginBottom: '0.25rem' }}>
      <button
        type="button"
        className="oc-campaign-picker"
        onClick={() => setOpen((o) => !o)}
        title={collapsed ? (active?.name ?? 'Select campaign') : undefined}
        style={{ justifyContent: collapsed ? 'center' : undefined, padding: collapsed ? '0.625rem' : undefined }}
      >
        {/* Coloured identity square */}
        <div style={{
          width: '1.75rem', height: '1.75rem', borderRadius: '0.375rem', flexShrink: 0,
          background: 'linear-gradient(135deg, var(--oc-accent) 0%, var(--s5) 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '0.625rem', fontWeight: 800, color: '#fff', fontFamily: 'var(--font-mono)',
        }}>
          {active ? active.name.slice(0, 2).toUpperCase() : 'PC'}
        </div>

        {!collapsed && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--oc-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.2 }}>
              {active ? active.name : <span style={{ color: 'var(--oc-muted)', fontWeight: 400 }}>Select campaign…</span>}
            </div>
            {active && (
              <div style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', marginTop: '0.125rem' }}>
                {active.company_count.toLocaleString()} companies
              </div>
            )}
          </div>
        )}

        {!collapsed && (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
            style={{ flexShrink: 0, color: 'var(--oc-muted)', transition: 'transform 160ms', transform: open ? 'rotate(180deg)' : 'none' }}>
            <polyline points="6 9 12 15 18 9" />
          </svg>
        )}
      </button>

      {open && !collapsed && (
        <div className="oc-nav-dropdown" style={{ left: '0.75rem', right: '0.75rem', minWidth: 'auto' }}>
          <div className="oc-nav-dropdown-scroll">
            {campaigns.length === 0
              ? <p style={{ padding: '0.625rem 0.875rem', fontSize: '0.875rem', color: 'var(--oc-muted)' }}>No campaigns yet.</p>
              : campaigns.map((c) => (
                  <button key={c.id} type="button" onClick={() => { onSelect(c.id); setOpen(false) }} className="oc-nav-dropdown-item">
                    <span className="oc-nav-dropdown-dot" style={{
                      backgroundColor: c.id === selectedId ? 'var(--oc-accent)' : 'transparent',
                      border: '1.5px solid var(--oc-border)',
                    }} />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: c.id === selectedId ? 600 : 400, color: c.id === selectedId ? 'var(--oc-accent-ink)' : 'var(--oc-text)' }}>
                      {c.name}
                    </span>
                    <span style={{ fontSize: '0.6875rem', color: 'var(--oc-muted)', flexShrink: 0 }}>
                      {c.company_count.toLocaleString()}
                    </span>
                  </button>
                ))}
          </div>
          <div className="oc-nav-dropdown-footer">
            <button type="button" onClick={() => { onManage(); setOpen(false) }} className="oc-nav-dropdown-link">
              + New campaign
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
