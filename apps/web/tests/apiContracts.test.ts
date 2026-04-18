import test from 'node:test'
import assert from 'node:assert/strict'

import { listContactCompanies, scrapeSelectedCompanies } from '../src/lib/api.ts'

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

test('listContactCompanies serializes match_gap_filter and upload_id', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { total: 0, has_more: false, limit: 50, offset: 0, items: [] }
  })

  await listContactCompanies({ matchGapFilter: 'contacts_no_match', uploadId: 'u-1' })

  assert.match(requested, /match_gap_filter=contacts_no_match/)
  assert.match(requested, /upload_id=u-1/)
})

test('scrapeSelectedCompanies sends idempotency header and scrape_rules body', async () => {
  let sentHeaders: Headers | undefined
  let sentBody = ''
  mockFetch((_url, init) => {
    sentHeaders = new Headers(init?.headers as HeadersInit)
    sentBody = String(init?.body ?? '')
    return { requested_count: 1, queued_count: 1, queued_job_ids: ['j1'], failed_company_ids: [] }
  })

  await scrapeSelectedCompanies(['c1'], {
    idempotencyKey: '0123456789abcdef',
    scrapeRules: { page_kinds: ['home', 'contact'] },
    uploadId: 'u-1',
  })

  assert.equal(sentHeaders?.get('X-Idempotency-Key'), '0123456789abcdef')
  assert.match(sentBody, /"page_kinds":\["home","contact"\]/)
  assert.match(sentBody, /"upload_id":"u-1"/)
})
