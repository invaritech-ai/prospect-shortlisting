import { useEffect, useState } from 'react'

interface RelativeTimeLabelProps {
  timestamp: string | null | undefined
  prefix?: string
}

function formatRelativeTime(timestamp: string | null | undefined, nowMs: number, prefix: string): string {
  if (!timestamp) return `${prefix} —`
  const ts = Date.parse(timestamp)
  if (Number.isNaN(ts)) return `${prefix} —`
  const deltaSeconds = Math.max(0, Math.floor((nowMs - ts) / 1000))
  if (deltaSeconds < 5) return `${prefix} just now`
  if (deltaSeconds < 60) return `${prefix} ${deltaSeconds}s ago`
  const deltaMinutes = Math.floor(deltaSeconds / 60)
  if (deltaMinutes < 60) return `${prefix} ${deltaMinutes}m ago`
  const deltaHours = Math.floor(deltaMinutes / 60)
  return `${prefix} ${deltaHours}h ago`
}

export function RelativeTimeLabel({ timestamp, prefix = 'Last updated' }: RelativeTimeLabelProps) {
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return <>{formatRelativeTime(timestamp, nowMs, prefix)}</>
}
