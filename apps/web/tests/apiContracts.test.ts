import test from 'node:test'
import assert from 'node:assert/strict'

import {
  listCompanies,
  listCompanyIds,
  listContactCompanies,
  listContacts,
  scrapeAllCompanies,
  scrapeSelectedCompanies,
} from '../src/lib/api.ts'

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

test('scrapeAllCompanies sends idempotency header and scrape_rules body', async () => {
  let sentHeaders: Headers | undefined
  let sentBody = ''
  mockFetch((_url, init) => {
    sentHeaders = new Headers(init?.headers as HeadersInit)
    sentBody = String(init?.body ?? '')
    return { requested_count: 2, queued_count: 1, queued_job_ids: ['j9'], failed_company_ids: [] }
  })

  await scrapeAllCompanies({
    idempotencyKey: 'all-0123456789',
    uploadId: 'u-2',
    scrapeRules: { page_kinds: ['home', 'contact'], fallback_enabled: true, fallback_limit: 1 },
  })

  assert.equal(sentHeaders?.get('X-Idempotency-Key'), 'all-0123456789')
  assert.match(sentBody, /"upload_id":"u-2"/)
  assert.match(sentBody, /"scrape_rules":\{"page_kinds":\["home","contact"\],"fallback_enabled":true,"fallback_limit":1\}/)
})

test('listContacts serializes letters and upload_id query params', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { total: 0, has_more: false, limit: 50, offset: 0, items: [] }
  })

  await listContacts({
    letters: ['w', 'x'],
    uploadId: 'upload-1',
    staleDays: 30,
  })

  assert.match(requested, /letters=w%2Cx/)
  assert.match(requested, /upload_id=upload-1/)
  assert.match(requested, /stale_days=30/)
})

test('listCompanies serializes multi-letter filters', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { total: 0, has_more: false, limit: 25, offset: 0, items: [] }
  })

  await listCompanies(25, 0, 'all', true, 'all', 'all', null, 'domain', 'asc', undefined, ['w', 'x'])

  assert.match(requested, /letters=w%2Cx/)
})

test('listCompanyIds serializes multi-letter filters', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { ids: [], total: 0 }
  })

  await listCompanyIds('all', 'all', 'all', null, undefined, ['w', 'x'])

  assert.match(requested, /letters=w%2Cx/)
})
