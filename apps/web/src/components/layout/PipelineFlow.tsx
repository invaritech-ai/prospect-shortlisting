import type { CompanyCounts, ContactCountsResponse } from '../../lib/types'
import type { ActiveView } from '../../lib/navigation'

type CompanyStageKey = 'uploaded' | 'scraped' | 'classified' | 'contact_ready'
type ContactStageKey = 'fetched' | 'verified' | 'campaign_ready'

const COMPANY_STAGES: Array<{ key: CompanyStageKey; label: string }> = [
  { key: 'uploaded', label: 'Uploaded' },
  { key: 'scraped', label: 'Scraped' },
  { key: 'classified', label: 'Classified' },
  { key: 'contact_ready', label: 'Contact Ready' },
]

const CONTACT_STAGES: Array<{ key: ContactStageKey; label: string }> = [
  { key: 'fetched', label: 'Fetched' },
  { key: 'verified', label: 'Verified' },
  { key: 'campaign_ready', label: 'Campaign Ready' },
]

interface PipelineFlowProps {
  activeView: ActiveView
  companyCounts: CompanyCounts | null
  contactCounts: ContactCountsResponse | null
  collapsed: boolean
  onNavigate: (view: ActiveView) => void
}

function CountPill({ n, active, color }: { n: number | null; active: boolean; color: 'blue' | 'emerald' }) {
  if (n === null) return null
  const colorCls = active
    ? color === 'blue'
      ? 'text-[var(--oc-accent-ink)] font-semibold'
      : 'text-emerald-800 font-semibold'
    : 'text-[var(--oc-muted)]'
  return (
    <span className={`font-mono text-[10px] tabular-nums shrink-0 ${colorCls}`}>
      {n.toLocaleString()}
    </span>
  )
}

function TrackStageRow({
  label,
  count,
  isLast,
  color,
  onClick,
}: {
  label: string
  count: number | null
  isLast: boolean
  color: 'blue' | 'emerald'
  onClick: () => void
}) {
  const lineColor = color === 'blue' ? 'bg-blue-100' : 'bg-emerald-100'
  const dotBorder = color === 'blue' ? 'border-blue-300 bg-blue-50' : 'border-emerald-300 bg-emerald-50'
  const dotEmpty = color === 'blue' ? 'border-blue-200 bg-white' : 'border-emerald-200 bg-white'
  const hoverText = color === 'blue' ? 'hover:text-[var(--oc-accent-ink)]' : 'hover:text-emerald-800'
  const hoverBg = color === 'blue' ? 'hover:bg-blue-50/70' : 'hover:bg-emerald-50/70'
  const hasItems = count !== null && count > 0

  return (
    <li className="flex">
      {/* Dot + vertical line gutter */}
      <div
        className="relative ml-[22px] mr-2.5 flex shrink-0 flex-col items-center"
        style={{ width: 10 }}
      >
        {/* Line below this dot (skip on last item) */}
        {!isLast && (
          <span className={`absolute top-[14px] left-1/2 -translate-x-1/2 w-px ${lineColor}`} style={{ bottom: 0 }} />
        )}
        {/* Dot */}
        <span
          className={`relative z-10 mt-[9px] h-2 w-2 shrink-0 rounded-full border transition ${hasItems ? dotBorder : dotEmpty}`}
        />
      </div>

      {/* Clickable row content */}
      <button
        type="button"
        onClick={onClick}
        className={`group flex flex-1 min-w-0 items-center gap-1.5 py-1.5 pr-3 text-left transition ${hoverBg} rounded-r-lg`}
      >
        <span className={`flex-1 min-w-0 truncate text-[11px] text-[var(--oc-muted)] ${hoverText} group-hover:text-inherit transition`}>
          {label}
        </span>
        <CountPill n={count} active={hasItems} color={color} />
      </button>
    </li>
  )
}

function TrackHeader({
  label,
  total,
  isActive,
  color,
  onClick,
}: {
  label: string
  total: number | null
  isActive: boolean
  color: 'blue' | 'emerald'
  onClick: () => void
}) {
  const dotActive = color === 'blue' ? 'bg-[var(--oc-accent)]' : 'bg-emerald-500'
  const dotInactive = color === 'blue' ? 'bg-blue-200' : 'bg-emerald-200'
  const labelActive = color === 'blue' ? 'text-[var(--oc-accent-ink)]' : 'text-emerald-800'
  const hoverBg = color === 'blue' ? 'hover:bg-blue-50/80' : 'hover:bg-emerald-50/80'

  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 px-3 py-2 transition ${hoverBg}`}
    >
      <span className={`h-2.5 w-2.5 shrink-0 rounded-sm transition ${isActive ? dotActive : dotInactive}`} />
      <span
        className={`flex-1 text-left text-[11px] font-bold transition ${isActive ? labelActive : 'text-[var(--oc-muted)]'}`}
      >
        {label}
      </span>
      {total !== null && (
        <span className="font-mono text-[10px] tabular-nums text-[var(--oc-muted)]">
          {total.toLocaleString()}
        </span>
      )}
    </button>
  )
}

export function PipelineFlow({
  activeView,
  companyCounts,
  contactCounts,
  collapsed,
  onNavigate,
}: PipelineFlowProps) {
  const companyActive = activeView === 's1-scraping' || activeView === 's2-ai' || activeView === 's3-contacts'
  const contactActive = activeView === 's4-validation'

  // ── Collapsed mini indicator ─────────────────────────────────
  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-2 py-1" aria-label="Pipeline stages">
        <button
          type="button"
          title="Companies pipeline"
          onClick={() => onNavigate('s1-scraping')}
          className={`h-2.5 w-2.5 rounded-sm transition ${companyActive ? 'bg-[var(--oc-accent)]' : 'bg-[var(--oc-border)] hover:bg-blue-300'}`}
        />
        <button
          type="button"
          title="Contacts pipeline"
          onClick={() => onNavigate('s4-validation')}
          className={`h-2.5 w-2.5 rounded-sm transition ${contactActive ? 'bg-emerald-500' : 'bg-[var(--oc-border)] hover:bg-emerald-300'}`}
        />
        <span
          className="h-2.5 w-2.5 rounded-sm bg-[var(--oc-border)] opacity-40 cursor-default"
          title="Email outreach (coming soon)"
        />
      </div>
    )
  }

  // ── Expanded pipeline flow ───────────────────────────────────
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--oc-border)] bg-[var(--oc-surface)]">
      {/* Widget label */}
      <div className="px-3 pt-2.5 pb-1">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--oc-muted)]">
          Pipeline
        </p>
      </div>

      {/* ── Company track ────────────────────────────────── */}
      <div className={`border-t border-[var(--oc-border)] transition ${companyActive ? 'bg-blue-50/50' : ''}`}>
        <TrackHeader
          label="Companies"
          total={companyCounts?.total ?? null}
          isActive={companyActive}
          color="blue"
          onClick={() => onNavigate('s1-scraping')}
        />
        <ul className="pb-1.5">
          {COMPANY_STAGES.map((stage, idx) => {
            const stageView: ActiveView =
              stage.key === 'uploaded' ? 's1-scraping'
              : stage.key === 'scraped' ? 's2-ai'
              : stage.key === 'classified' ? 's3-contacts'
              : 's4-validation'
            return (
              <TrackStageRow
                key={stage.key}
                label={stage.label}
                count={companyCounts?.[stage.key] ?? null}
                isLast={idx === COMPANY_STAGES.length - 1}
                color="blue"
                onClick={() => onNavigate(stageView)}
              />
            )
          })}
        </ul>
      </div>

      {/* ── Contact track ────────────────────────────────── */}
      <div className={`border-t border-[var(--oc-border)] transition ${contactActive ? 'bg-emerald-50/50' : ''}`}>
        <TrackHeader
          label="Contacts"
          total={contactCounts?.total ?? null}
          isActive={contactActive}
          color="emerald"
          onClick={() => onNavigate('s4-validation')}
        />
        <ul className="pb-1.5">
          {CONTACT_STAGES.map((stage, idx) => (
            <TrackStageRow
              key={stage.key}
              label={stage.label}
              count={contactCounts?.[stage.key] ?? null}
              isLast={idx === CONTACT_STAGES.length - 1}
              color="emerald"
              onClick={() => onNavigate('s4-validation')}
            />
          ))}
        </ul>
      </div>

      {/* ── Email track — coming soon ─────────────────────── */}
      <div className="border-t border-[var(--oc-border)]">
        <div className="flex items-center gap-2 px-3 py-2">
          <span className="h-2.5 w-2.5 shrink-0 rounded-sm bg-slate-200" />
          <span className="flex-1 text-[11px] font-bold text-slate-400">Email Outreach</span>
          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-slate-400">
            Soon
          </span>
        </div>
      </div>
    </div>
  )
}
