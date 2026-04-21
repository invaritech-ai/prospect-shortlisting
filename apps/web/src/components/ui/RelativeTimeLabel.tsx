import { useEffect, useRef, useSyncExternalStore } from 'react'

interface RelativeTimeLabelProps {
  timestamp: string | null | undefined
  prefix?: string
}

const RECENT_TICK_MS = 1_000
const STALE_TICK_MS = 60_000
const RECENT_THRESHOLD_MS = 60_000

const tickerListeners = new Set<() => void>()
const trackedTimestamps = new Map<number, number | null>()
let tickerNowMs = Date.now()
let tickerTimer: number | null = null
let nextTickerId = 1

function emitTicker(): void {
  tickerNowMs = Date.now()
  for (const listener of tickerListeners) listener()
}

function scheduleTicker(): void {
  if (typeof window === 'undefined') return
  if (tickerTimer !== null) window.clearTimeout(tickerTimer)
  if (tickerListeners.size === 0) {
    tickerTimer = null
    return
  }
  const now = Date.now()
  const hasRecentTimestamp = [...trackedTimestamps.values()].some(
    (timestampMs) => timestampMs != null && now - timestampMs < RECENT_THRESHOLD_MS,
  )
  const delay = hasRecentTimestamp ? RECENT_TICK_MS : STALE_TICK_MS
  tickerTimer = window.setTimeout(() => {
    emitTicker()
    scheduleTicker()
  }, delay)
}

function subscribeTicker(listener: () => void): () => void {
  tickerListeners.add(listener)
  scheduleTicker()
  return () => {
    tickerListeners.delete(listener)
    scheduleTicker()
  }
}

function getTickerSnapshot(): number {
  return tickerNowMs
}

function updateTrackedTimestamp(id: number, timestamp: string | null | undefined): void {
  const ts = timestamp ? Date.parse(timestamp) : Number.NaN
  trackedTimestamps.set(id, Number.isNaN(ts) ? null : ts)
  scheduleTicker()
}

function removeTrackedTimestamp(id: number): void {
  trackedTimestamps.delete(id)
  scheduleTicker()
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
  const idRef = useRef(0)
  if (idRef.current === 0) idRef.current = nextTickerId++
  const nowMs = useSyncExternalStore(subscribeTicker, getTickerSnapshot, getTickerSnapshot)

  useEffect(() => {
    updateTrackedTimestamp(idRef.current, timestamp)
    return () => removeTrackedTimestamp(idRef.current)
  }, [timestamp])

  useEffect(() => {
    emitTicker()
  }, [])

  return <>{formatRelativeTime(timestamp, nowMs, prefix)}</>
}
