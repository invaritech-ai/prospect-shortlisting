import { useEffect, useState } from 'react'

interface RelativeTimeLabelProps {
  timestamp: string | null | undefined
  prefix?: string
}

function formatRelativeTime(timestamp: string | null | undefined, nowMs: number, prefix: string): string {
  const lead = prefix ? `${prefix} ` : ''
  if (!timestamp) return prefix ? `${prefix} —` : '—'
  const ts = Date.parse(timestamp)
  if (Number.isNaN(ts)) return prefix ? `${prefix} —` : '—'
  const deltaSeconds = Math.max(0, Math.floor((nowMs - ts) / 1000))
  if (deltaSeconds < 5) return `${lead}just now`.trimStart()
  if (deltaSeconds < 60) return `${lead}${deltaSeconds}s ago`.trimStart()
  const deltaMinutes = Math.floor(deltaSeconds / 60)
  if (deltaMinutes < 60) return `${lead}${deltaMinutes}m ago`.trimStart()
  const deltaHours = Math.floor(deltaMinutes / 60)
  return `${lead}${deltaHours}h ago`.trimStart()
}

export function RelativeTimeLabel({ timestamp, prefix = 'Last updated' }: RelativeTimeLabelProps) {
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return <>{formatRelativeTime(timestamp, nowMs, prefix)}</>
}
