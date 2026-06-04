import { LiveDot } from '../../ui/LiveDot'

type StageView = 's1-scraping' | 's2-ai' | 's3-contacts' | 's4-validation'

export interface StageCardDef {
  view: StageView
  stageNum: string
  label: string
  color: string
  bg: string
  textColor: string
  glow: string
  count: number
  hint: string
  isLive: boolean
  liveLabel: string
}

interface StageCardsProps {
  cards: StageCardDef[]
  hasSelectedCampaign: boolean
  onNavigate: (view: StageView) => void
  onOpenCampaigns: () => void
}

export function StageCards({ cards, hasSelectedCampaign, onNavigate, onOpenCampaigns }: StageCardsProps) {
  return (
    <section>
      <p className="oc-label" style={{ marginBottom: '0.875rem' }}>Stages</p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map((card) => (
          <button
            key={card.view}
            type="button"
            onClick={() => hasSelectedCampaign ? onNavigate(card.view) : onOpenCampaigns()}
            className="oc-stage-card"
            style={{
              backgroundColor: card.bg,
              borderColor: `color-mix(in srgb, ${card.color} 28%, white)`,
              '--card-glow': card.glow,
            } as React.CSSProperties}
          >
            {/* Stage number + live indicator */}
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.18em', color: card.color }}>
                {card.stageNum}
              </span>
              {card.isLive && (
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.625rem', fontWeight: 600, color: card.color }}>
                  <LiveDot color={card.color} />
                  {card.liveLabel}
                </span>
              )}
            </span>

            {/* Big count */}
            <span style={{
              fontFamily: 'var(--font-mono)', fontWeight: 700,
              fontSize: 'clamp(2rem, 5vw, 2.75rem)', lineHeight: 1,
              letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums',
              color: card.color,
            }}>
              {card.count.toLocaleString()}
            </span>

            {/* Label + hint */}
            <span>
              <span style={{ display: 'block', fontWeight: 700, fontSize: '1rem', color: card.textColor, lineHeight: 1.2 }}>
                {card.label}
              </span>
              <span style={{ display: 'block', fontSize: '0.75rem', color: card.color, opacity: 0.7, marginTop: '0.2rem' }}>
                {card.hint}
              </span>
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
