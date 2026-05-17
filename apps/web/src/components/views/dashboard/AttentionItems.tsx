interface AttentionItem {
  key: string
  color: string
  bg: string
  icon: string
  text: string
  action: string
  onAction: () => void
}

interface AttentionItemsProps {
  items: AttentionItem[]
}

export function AttentionItems({ items }: AttentionItemsProps) {
  if (items.length === 0) return null

  return (
    <section>
      <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Needs Your Attention</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {items.map((item) => (
          <div key={item.key} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: '1rem', flexWrap: 'wrap',
            borderRadius: '0.875rem', padding: '0.875rem 1rem',
            backgroundColor: item.bg,
            border: `1px solid color-mix(in srgb, ${item.color} 20%, white)`,
            borderLeft: `3px solid ${item.color}`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', minWidth: 0 }}>
              <span style={{ fontSize: '0.875rem', fontWeight: 700, color: item.color, flexShrink: 0 }}>{item.icon}</span>
              <p style={{ margin: 0, fontSize: '0.9375rem', color: 'var(--oc-text)', lineHeight: 1.4 }}>{item.text}</p>
            </div>
            <button
              type="button"
              onClick={item.onAction}
              className="oc-btn oc-btn-secondary oc-btn-sm"
              style={{ flexShrink: 0, borderColor: `color-mix(in srgb, ${item.color} 30%, white)`, color: item.color }}
            >
              {item.action} →
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}

export type { AttentionItem }
