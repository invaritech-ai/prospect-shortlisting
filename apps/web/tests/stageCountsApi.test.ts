import test from 'node:test'
import assert from 'node:assert/strict'

import { getCampaignStageCounts } from '../src/lib/api.ts'

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  ;(globalThis as { fetch: typeof fetch }).fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const body = handler(String(input), init)
    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => body,
      text: async () => JSON.stringify(body),
    } as Response
  }) as typeof fetch
}

test('getCampaignStageCounts requests the shared campaign stage-count endpoint', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return {
      campaign_id: 'camp-1',
      updated_at: '2026-05-31T00:00:00Z',
      scraping: { badge: 0, total: 0, pending: 0, queued: 0, running: 0, succeeded: 0, failed: 0, retryable_failed: 0, is_live: false },
      ai_review: { badge: 0, all: 0, unclassified: 0, possible: 0, unknown: 0, crap: 0, queued: 0, running: 0, is_live: false },
      contacts: { badge: 0, all: 0, pending: 0, running: 0, done: 0, failed: 0, no_match: 0, contacts_found: 0, emails_found: 0, fetched_people_found: 0, is_live: false },
      validation: {
        badge: 0,
        total: 0,
        pending: 0,
        checking: 0,
        stale: 0,
        valid: 0,
        undeliverable: 0,
        catch_all: 0,
        failed: 0,
        unknown: 0,
        running: 0,
        invalid: 0,
        is_live: false,
      },
    }
  })

  await getCampaignStageCounts('camp-1')

  assert.match(requested, /\/v1\/campaigns\/camp-1\/stage-counts$/)
})
