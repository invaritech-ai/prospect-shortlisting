import type { ReactNode } from 'react'
import { RelativeTimeLabel } from '../../ui/RelativeTimeLabel'

type PipelineStageCompanyLinkRow = {
  id: string
  domain: string
  normalized_url: string | null
  raw_url: string
  last_activity: string | null
}

/** Leading checkbox + domain + last-activity columns shared across S1–S3 company tables */
export function PipelineStageCompanyTableRow({
  company: c,
  selected,
  checkboxDisabled,
  onToggle,
  stageAccentVar,
  stageBgVar,
  children,
}: {
  company: PipelineStageCompanyLinkRow
  selected: boolean
  checkboxDisabled: boolean
  onToggle: () => void
  stageAccentVar: string
  stageBgVar: string
  children: ReactNode
}) {
  return (
    <tr
      className="border-b border-(--oc-border) last:border-0 transition"
      style={selected ? { backgroundColor: `var(${stageBgVar})` } : undefined}
    >
      <td className="p-3">
        <input
          type="checkbox"
          disabled={checkboxDisabled}
          checked={selected}
          onChange={onToggle}
          className="cursor-pointer disabled:cursor-not-allowed"
        />
      </td>
      <td className="p-3">
        <a
          href={c.normalized_url || c.raw_url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-[12px] font-medium hover:underline"
          style={{ color: `var(${stageAccentVar})` }}
        >
          {c.domain}
        </a>
      </td>
      <td className="p-3 text-[11px] text-(--oc-muted) tabular-nums">
        <RelativeTimeLabel timestamp={c.last_activity} prefix="" />
      </td>
      {children}
    </tr>
  )
}
