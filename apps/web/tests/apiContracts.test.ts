import test from 'node:test'
import assert from 'node:assert/strict'

import {
  createEmailFetchBatch,
  createEmailVerificationBatch,
  downloadFreshValidEmailCsv,
  getActiveEmailFetchBatch,
  getActiveEmailVerificationBatch,
  getAiReviewLabelCounts,
  getCampaignCosts,
  getEmailFetchLetterCounts,
  getEmailVerificationBatch,
  getEmailVerificationLetterCounts,
  getIntegrationSettings,
  listAiReviewDomains,
  listDomains,
  listEmailFetchCompanyIds,
  listEmailFetchCompanies,
  listEmailVerificationContactIds,
  listEmailVerificationContacts,
  previewEmailFetch,
  previewEmailVerification,
  testIntegrationProvider,
  updateIntegrationProvider,
} from '../src/lib/api.ts'

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  ;(globalThis as { fetch: typeof fetch }).fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const body = handler(String(input), init)
    const text = typeof body === 'string' ? body : JSON.stringify(body)
    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => body,
      text: async () => text,
      blob: async () => new Blob([text], { type: 'text/csv' }),
    } as Response
  }) as typeof fetch
}

test('getIntegrationSettings requests the masked integrations endpoint', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { store_available: true, providers: [] }
  })

  await getIntegrationSettings()

  assert.match(requested, /\/v1\/settings\/integrations$/)
})

test('updateIntegrationProvider serializes provider field updates', async () => {
  let requested = ''
  let method = ''
  let sentBody = ''
  mockFetch((url, init) => {
    requested = url
    method = String(init?.method ?? '')
    sentBody = String(init?.body ?? '')
    return {
      provider: 'openrouter',
      label: 'OpenRouter',
      description: 'Primary LLM gateway',
      fields: [{ field: 'api_key', is_set: true, source: 'db', last4: '9999', updated_at: '2026-04-20T00:00:00Z' }],
    }
  })

  await updateIntegrationProvider('openrouter', {
    fields: [{ field: 'api_key', value: 'db-openrouter-9999' }],
  })

  assert.equal(method, 'PUT')
  assert.match(requested, /\/v1\/settings\/integrations\/openrouter$/)
  assert.match(sentBody, /"field":"api_key"/)
  assert.match(sentBody, /"value":"db-openrouter-9999"/)
})

test('testIntegrationProvider posts to provider test endpoint', async () => {
  let requested = ''
  let method = ''
  mockFetch((url, init) => {
    requested = url
    method = String(init?.method ?? '')
    return { provider: 'apollo', ok: true, source: 'env', error_code: '', message: 'Credentials look valid.' }
  })

  await testIntegrationProvider('apollo')

  assert.equal(method, 'POST')
  assert.match(requested, /\/v1\/settings\/integrations\/apollo\/test$/)
})

test('listDomains serializes current company filters', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { total: 0, limit: 50, offset: 0, items: [] }
  })

  await listDomains('camp-1', {
    uploadId: 'upload-1',
    scrapeStatus: 'soft-failures',
    letter: 'A',
    search: ' acme ',
    limit: 25,
    offset: 50,
  })

  assert.match(requested, /\/v1\/companies\?/)
  assert.match(requested, /campaign_id=camp-1/)
  assert.match(requested, /upload_id=upload-1/)
  assert.match(requested, /scrape_status=soft-failures/)
  assert.match(requested, /letter=A/)
  assert.match(requested, /search=acme/)
  assert.match(requested, /limit=25/)
  assert.match(requested, /offset=50/)
})

test('AI review APIs serialize label and search filters', async () => {
  const requested: string[] = []
  mockFetch((url) => {
    requested.push(url)
    return { total: 0, limit: 50, offset: 0, items: [] }
  })

  await listAiReviewDomains('camp-1', { label: 'possible', letter: 'B', search: ' beta ' })
  await getAiReviewLabelCounts('camp-1', { letter: 'C', search: ' gamma ' })

  assert.match(requested[0], /\/v1\/ai-review\/domains\?/)
  assert.match(requested[0], /campaign_id=camp-1/)
  assert.match(requested[0], /label=possible/)
  assert.match(requested[0], /letter=B/)
  assert.match(requested[0], /search=beta/)
  assert.match(requested[1], /\/v1\/ai-review\/label-counts\?/)
  assert.match(requested[1], /letter=C/)
  assert.match(requested[1], /search=gamma/)
})

test('email fetch APIs use the S3 namespace and query params', async () => {
  const requested: string[] = []
  mockFetch((url) => {
    requested.push(url)
    return { total: 0, limit: 200, offset: 0, counts: {}, items: [] }
  })

  await listEmailFetchCompanies('camp-1', { status: 'pending', letter: 'D', search: ' delta ', limit: 100, offset: 20 })
  await listEmailFetchCompanyIds('camp-1', { status: 'failed', letter: 'E', search: ' echo ', fetchableOnly: true })
  await getEmailFetchLetterCounts('camp-1', { status: 'done', search: ' foxtrot ' })
  await getActiveEmailFetchBatch('camp-1')

  assert.match(requested[0], /\/v1\/email-fetch\/companies\?/)
  assert.match(requested[0], /campaign_id=camp-1/)
  assert.match(requested[0], /status=pending/)
  assert.match(requested[0], /letter=D/)
  assert.match(requested[0], /search=delta/)
  assert.match(requested[0], /limit=100/)
  assert.match(requested[0], /offset=20/)
  assert.match(requested[1], /\/v1\/email-fetch\/company-ids\?/)
  assert.match(requested[1], /fetchable_only=true/)
  assert.match(requested[2], /\/v1\/email-fetch\/letter-counts\?/)
  assert.match(requested[2], /status=done/)
  assert.match(requested[2], /search=foxtrot/)
  assert.match(requested[3], /\/v1\/email-fetch\/batches\/active\?campaign_id=camp-1$/)
})

test('email fetch preview and batch post domain ids', async () => {
  const requested: string[] = []
  const bodies: string[] = []
  mockFetch((url, init) => {
    requested.push(url)
    bodies.push(String(init?.body ?? ''))
    return { id: 'batch-1', campaign_id: 'camp-1', state: 'queued' }
  })

  await previewEmailFetch({ campaign_id: 'camp-1', domain_ids: ['d1', 'd2'], mode: 'fetch' })
  await createEmailFetchBatch({ campaign_id: 'camp-1', domain_ids: ['d1', 'd2'], mode: 'fetch' })

  assert.match(requested[0], /\/v1\/email-fetch\/preview$/)
  assert.match(requested[1], /\/v1\/email-fetch\/batches$/)
  assert.match(bodies[0], /"domain_ids":\["d1","d2"\]/)
  assert.match(bodies[1], /"domain_ids":\["d1","d2"\]/)
})

test('getCampaignCosts requests campaign costs endpoint', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return {
      pipeline_run_id: null,
      campaign_id: 'camp-1',
      company_id: null,
      total_cost_usd: '0.000000',
      event_count: 0,
      input_tokens: 0,
      output_tokens: 0,
      by_stage: {},
    }
  })

  await getCampaignCosts('camp-1')

  assert.match(requested, /\/v1\/campaigns\/camp-1\/costs$/)
})

test('email verification APIs use the S4 namespace and query params', async () => {
  const requested: string[] = []
  mockFetch((url) => {
    requested.push(url)
    return { total: 0, limit: 50, offset: 0, counts: {}, items: [] }
  })

  await listEmailVerificationContacts('camp-1', {
    status: 'pending',
    letter: 'A',
    search: ' ada ',
    limit: 50,
    offset: 0,
  })

  assert.match(requested[0], /\/v1\/email-verification\/contacts\?/)
  assert.match(requested[0], /campaign_id=camp-1/)
  assert.match(requested[0], /status=pending/)
  assert.match(requested[0], /letter=A/)
  assert.match(requested[0], /search=ada/)
  assert.match(requested[0], /limit=50/)
  assert.match(requested[0], /offset=0/)
})

test('email verification preview and batch post contact ids', async () => {
  const requested: string[] = []
  const methods: string[] = []
  const bodies: string[] = []
  mockFetch((url, init) => {
    requested.push(url)
    methods.push(String(init?.method ?? ''))
    bodies.push(String(init?.body ?? ''))
    return {
      id: 'batch-1',
      campaign_id: 'camp-1',
      state: 'queued',
      selected_count: 2,
      queued_count: 2,
      verified_count: 0,
      valid_count: 0,
      invalid_count: 0,
      skipped_count: 0,
      result_summary: null,
      created_at: '2026-06-04T00:00:00Z',
      finished_at: null,
    }
  })

  await previewEmailVerification({ campaign_id: 'camp-1', contact_ids: ['c1', 'c2'] })
  await createEmailVerificationBatch({ campaign_id: 'camp-1', contact_ids: ['c1', 'c2'] })

  assert.match(requested[0], /\/v1\/email-verification\/preview$/)
  assert.match(requested[1], /\/v1\/email-verification\/batches$/)
  assert.equal(methods[0], 'POST')
  assert.equal(methods[1], 'POST')
  assert.match(bodies[0], /"campaign_id":"camp-1"/)
  assert.match(bodies[0], /"contact_ids":\["c1","c2"\]/)
  assert.match(bodies[1], /"campaign_id":"camp-1"/)
  assert.match(bodies[1], /"contact_ids":\["c1","c2"\]/)
})

test('email verification helper APIs use S4 support endpoints', async () => {
  const requested: string[] = []
  mockFetch((url) => {
    requested.push(url)
    return { ids: [], total: 0, limit: 200, offset: 0 }
  })

  await listEmailVerificationContactIds('camp-1', {
    status: 'stale',
    letter: 'B',
    search: ' beta ',
    actionableOnly: true,
    limit: 200,
    offset: 10,
  })
  await getEmailVerificationLetterCounts('camp-1', { status: 'valid', search: ' gamma ' })
  await getEmailVerificationBatch('batch-1')
  await getActiveEmailVerificationBatch('camp-1')

  assert.match(requested[0], /\/v1\/email-verification\/contact-ids\?/)
  assert.match(requested[0], /campaign_id=camp-1/)
  assert.match(requested[0], /status=stale/)
  assert.match(requested[0], /letter=B/)
  assert.match(requested[0], /search=beta/)
  assert.match(requested[0], /actionable_only=true/)
  assert.match(requested[0], /limit=200/)
  assert.match(requested[0], /offset=10/)
  assert.match(requested[1], /\/v1\/email-verification\/letter-counts\?/)
  assert.match(requested[1], /campaign_id=camp-1/)
  assert.match(requested[1], /status=valid/)
  assert.match(requested[1], /search=gamma/)
  assert.match(requested[2], /\/v1\/email-verification\/batches\/batch-1$/)
  assert.match(requested[3], /\/v1\/email-verification\/batches\/active\?campaign_id=camp-1$/)
})

test('email verification export downloads fresh valid CSV from S4 endpoint', async () => {
  const requested: string[] = []
  const credentials: Array<RequestCredentials | undefined> = []
  mockFetch((url, init) => {
    requested.push(url)
    credentials.push(init?.credentials)
    return 'first_name,last_name,title,company_domain,email,linkedin_url,verified_at\nAda,Lovelace,Marketing Director,example.com,ada@example.com,https://linkedin.com/in/ada,2026-06-04T00:00:00Z\n'
  })

  const clicked: Array<{ href: string; download: string }> = []
  const revoked: string[] = []
  const previousDocument = (globalThis as { document?: Document }).document
  const previousCreateObjectUrl = URL.createObjectURL
  const previousRevokeObjectUrl = URL.revokeObjectURL
  ;(globalThis as { document?: Document }).document = {
    body: {
      appendChild: () => undefined,
    },
    createElement: () => ({
      href: '',
      download: '',
      style: {},
      click() {
        clicked.push({ href: this.href, download: this.download })
      },
      remove() {
        return undefined
      },
    }),
  } as unknown as Document
  URL.createObjectURL = () => 'blob:s4-valid-export'
  URL.revokeObjectURL = (url: string) => { revoked.push(url) }

  try {
    await downloadFreshValidEmailCsv('camp-1')
  } finally {
    ;(globalThis as { document?: Document }).document = previousDocument
    URL.createObjectURL = previousCreateObjectUrl
    URL.revokeObjectURL = previousRevokeObjectUrl
  }

  assert.match(requested[0], /\/v1\/email-verification\/exports\/valid\.csv\?campaign_id=camp-1$/)
  assert.equal(credentials[0], 'include')
  assert.deepEqual(clicked, [{ href: 'blob:s4-valid-export', download: 'valid-emails-camp-1.csv' }])
  assert.deepEqual(revoked, ['blob:s4-valid-export'])
})
