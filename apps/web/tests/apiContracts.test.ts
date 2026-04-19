import test from 'node:test'
import assert from 'node:assert/strict'

import {
  activateScrapePrompt,
  createScrapePrompt,
  listCompanies,
  listCompanyIds,
  listContactCompanies,
  listContacts,
  listScrapePrompts,
  scrapeAllCompanies,
  scrapeSelectedCompanies,
  updateScrapePrompt,
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
    scrapeRules: { page_kinds: ['home', 'contact'], classifier_prompt_text: 'Find the best URL for each of these page types:\n- home\n- contact' },
    uploadId: 'u-1',
  })

  assert.equal(sentHeaders?.get('X-Idempotency-Key'), '0123456789abcdef')
  assert.match(sentBody, /"page_kinds":\["home","contact"\]/)
  assert.match(sentBody, /"classifier_prompt_text":"Find the best URL for each of these page types:\\n- home\\n- contact"/)
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

test('createScrapePrompt serializes intent_text', async () => {
  let sentBody = ''
  mockFetch((_url, init) => {
    sentBody = String(init?.body ?? '')
    return {
      id: 'sp1',
      name: 'Scrape Prompt',
      enabled: true,
      is_system_default: false,
      is_active: false,
      intent_text: 'Find pricing and contact pages',
      compiled_prompt_text: 'Find the best URL for each of these page types:\\n- pricing\\n- contact',
      scrape_rules_structured: { page_kinds: ['pricing', 'contact'] },
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
  })

  await createScrapePrompt({
    name: 'Scrape Prompt',
    intent_text: 'Find pricing and contact pages',
    enabled: true,
  })

  assert.match(sentBody, /"intent_text":"Find pricing and contact pages"/)
})

test('updateScrapePrompt serializes intent_text', async () => {
  let sentBody = ''
  mockFetch((_url, init) => {
    sentBody = String(init?.body ?? '')
    return {
      id: 'sp1',
      name: 'Scrape Prompt',
      enabled: true,
      is_system_default: false,
      is_active: false,
      intent_text: 'Find team and leadership pages',
      compiled_prompt_text: 'Find the best URL for each of these page types:\\n- team\\n- leadership',
      scrape_rules_structured: { page_kinds: ['team', 'leadership'] },
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
  })

  await updateScrapePrompt('sp1', { intent_text: 'Find team and leadership pages' })

  assert.match(sentBody, /"intent_text":"Find team and leadership pages"/)
})

test('listScrapePrompts serializes enabled_only', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return []
  })

  await listScrapePrompts(true)

  assert.match(requested, /enabled_only=true/)
})

test('activateScrapePrompt posts to activate endpoint', async () => {
  let requested = ''
  let method = ''
  mockFetch((url, init) => {
    requested = url
    method = String(init?.method ?? '')
    return {
      id: 'sp1',
      name: 'Default S1 Scrape Prompt',
      enabled: true,
      is_system_default: true,
      is_active: true,
      intent_text: null,
      compiled_prompt_text: 'Find the best URL for each of these page types:',
      scrape_rules_structured: { page_kinds: ['about'] },
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
  })

  await activateScrapePrompt('sp1')

  assert.match(requested, /\/v1\/scrape-prompts\/sp1\/activate$/)
  assert.equal(method, 'POST')
})
