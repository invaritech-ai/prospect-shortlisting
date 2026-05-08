import { useEffect, useRef } from 'react'

const viteEnv = (import.meta as { env?: Record<string, string | undefined> }).env
const API_BASE_URL = (
  viteEnv?.VITE_API_BASE_URL ??
  (globalThis as { __API_BASE_URL__?: string }).__API_BASE_URL__ ??
  'http://localhost:8000'
).replace(/\/+$/, '')

export interface CampaignEvent {
  id?: number
  stage?: string
  job_id?: string
  from_state?: string | null
  to_state?: string | null
  event_type?: string | null
  created_at?: string
}

/**
 * Subscribe to live job-events for a campaign via SSE.
 * Existing polling stays in place as a fallback — this hook only adds
 * a faster nudge when something changes server-side.
 *
 * Reconnects automatically on network errors (browser EventSource default
 * is to auto-reconnect; we additionally rebuild it after hard failures).
 */
export function useCampaignEventStream(
  campaignId: string | null,
  onEvent: (ev: CampaignEvent) => void,
  enabled: boolean = true,
): void {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    if (!enabled || !campaignId) return
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') return

    let es: EventSource | null = null
    let cancelled = false
    let retry: number | null = null
    let backoff = 1000

    const open = () => {
      if (cancelled) return
      const url = `${API_BASE_URL}/v1/campaigns/${encodeURIComponent(campaignId)}/events/stream`
      es = new EventSource(url, { withCredentials: true })
      es.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data) as CampaignEvent
          handlerRef.current(data)
          backoff = 1000
        } catch {
          /* ignore malformed payloads */
        }
      }
      es.onerror = () => {
        if (es) {
          es.close()
          es = null
        }
        if (cancelled) return
        // The browser would auto-reconnect, but on hard 503s it gives up.
        // Schedule an explicit retry with capped exponential backoff.
        retry = window.setTimeout(open, backoff)
        backoff = Math.min(backoff * 2, 30000)
      }
    }

    open()
    return () => {
      cancelled = true
      if (retry !== null) window.clearTimeout(retry)
      if (es) es.close()
    }
  }, [campaignId, enabled])
}
