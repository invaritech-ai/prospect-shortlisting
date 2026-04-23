import test from 'node:test'
import assert from 'node:assert/strict'

import {
  activateScrapePrompt,
  createScrapePrompt,
  getCampaignCosts,
  getCostStats,
  getIntegrationSettings,
  getCompaniesExportUrl,
  getContactsExportUrl,
  getPipelineRunCosts,
  getPipelineRunProgress,
  listCompanies,
  listCompanyIds,
  listContactCompanies,
  listContacts,
  listScrapePrompts,
  startPipelineRun,
  scrapeAllCompanies,
  scrapeSelectedCompanies,
  testIntegrationProvider,
  updateIntegrationProvider,
  updateScrapePrompt,
  previewTitleRuleImpact,
  queueTitleRuleImpactFetch,
  verifyContacts,
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

  await listContactCompanies({ campaignId: 'camp-1', matchGapFilter: 'contacts_no_match', uploadId: 'u-1' })

  assert.match(requested, /match_gap_filter=contacts_no_match/)
  assert.match(requested, /upload_id=u-1/)
})

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

test('scrapeSelectedCompanies sends idempotency header and scrape_rules body', async () => {
  let sentHeaders: Headers | undefined
  let sentBody = ''
  mockFetch((_url, init) => {
    sentHeaders = new Headers(init?.headers as HeadersInit)
    sentBody = String(init?.body ?? '')
    return { requested_count: 1, queued_count: 1, queued_job_ids: ['j1'], failed_company_ids: [] }
  })

  await scrapeSelectedCompanies('campaign-1', ['c1'], {
    idempotencyKey: '0123456789abcdef',
    scrapeRules: { page_kinds: ['home', 'contact'], classifier_prompt_text: 'Find the best URL for each of these page types:\n- home\n- contact' },
    uploadId: 'u-1',
  })

  assert.equal(sentHeaders?.get('X-Idempotency-Key'), '0123456789abcdef')
  assert.match(sentBody, /"campaign_id":"campaign-1"/)
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
    campaignId: 'camp-1',
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

  await listCompanies('camp-1', 25, 0, 'all', true, 'all', 'all', null, 'domain', 'asc', undefined, ['w', 'x'])

  assert.match(requested, /letters=w%2Cx/)
})

test('listCompanies serializes full pipeline status and search filters', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { total: 0, has_more: false, limit: 25, offset: 0, items: [] }
  })

  await listCompanies('camp-1', 25, 0, 'all', true, 'all', 'all', 'a', 'domain', 'asc', undefined, undefined, 'soft-failures', ' acme ')

  assert.match(requested, /letter=a/)
  assert.match(requested, /status_filter=soft-failures/)
  assert.match(requested, /search=acme/)
})

test('listCompanyIds serializes multi-letter filters', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { ids: [], total: 0 }
  })

  await listCompanyIds('camp-1', 'all', 'all', 'all', null, undefined, ['w', 'x'])

  assert.match(requested, /letters=w%2Cx/)
})

test('listCompanyIds serializes full pipeline status and search filters', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { ids: [], total: 0 }
  })

  await listCompanyIds('camp-1', 'all', 'all', 'all', 'b', undefined, undefined, 'complete', ' beta ')

  assert.match(requested, /letter=b/)
  assert.match(requested, /status_filter=complete/)
  assert.match(requested, /search=beta/)
})

test('getLetterCounts serializes full pipeline status and search filters', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { counts: {} }
  })

  const { getLetterCounts } = await import('../src/lib/api.ts')
  await getLetterCounts('camp-1', 'all', 'all', 'all', undefined, 'permanent-failures', ' gamma ')

  assert.match(requested, /status_filter=permanent-failures/)
  assert.match(requested, /search=gamma/)
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

test('startPipelineRun posts campaign-scoped payload', async () => {
  let requested = ''
  let method = ''
  let sentBody = ''
  mockFetch((url, init) => {
    requested = url
    method = String(init?.method ?? '')
    sentBody = String(init?.body ?? '')
    return {
      pipeline_run_id: 'run-1',
      requested_count: 10,
      reused_count: 2,
      queued_count: 7,
      skipped_count: 1,
      failed_count: 0,
    }
  })

  await startPipelineRun({
    campaign_id: 'camp-1',
    scrape_rules_snapshot: { page_kinds: ['home', 'contact'] },
    analysis_prompt_snapshot: { prompt_id: 'p-1', prompt_text: 'Label ICP fit' },
  })

  assert.match(requested, /\/v1\/pipeline-runs\/start$/)
  assert.equal(method, 'POST')
  assert.match(sentBody, /"campaign_id":"camp-1"/)
  assert.match(sentBody, /"scrape_rules_snapshot":\{"page_kinds":\["home","contact"\]\}/)
  assert.match(sentBody, /"analysis_prompt_snapshot":\{"prompt_id":"p-1","prompt_text":"Label ICP fit"\}/)
})

test('getPipelineRunProgress requests run progress endpoint', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return {
      pipeline_run_id: 'run-1',
      campaign_id: 'camp-1',
      status: 'queued',
      requested_count: 5,
      reused_count: 0,
      queued_count: 5,
      skipped_count: 0,
      failed_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      started_at: null,
      finished_at: null,
      stages: {},
    }
  })

  await getPipelineRunProgress('run-1')
  assert.match(requested, /\/v1\/pipeline-runs\/run-1\/progress$/)
})

test('getPipelineRunCosts requests run costs endpoint', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return {
      pipeline_run_id: 'run-1',
      campaign_id: 'camp-1',
      company_id: null,
      total_cost_usd: '0.100000',
      event_count: 1,
      input_tokens: 10,
      output_tokens: 5,
      by_stage: {},
    }
  })

  await getPipelineRunCosts('run-1')
  assert.match(requested, /\/v1\/pipeline-runs\/run-1\/costs$/)
})

test('getCampaignCosts requests campaign costs endpoint', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return {
      pipeline_run_id: null,
      campaign_id: 'camp-1',
      company_id: null,
      total_cost_usd: '0.100000',
      event_count: 1,
      input_tokens: 10,
      output_tokens: 5,
      by_stage: {},
    }
  })

  await getCampaignCosts('camp-1')
  assert.match(requested, /\/v1\/campaigns\/camp-1\/costs$/)
})

test('getCostStats serializes campaign_id and paging params', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return { currency: 'USD', window_days: 30, totals: {}, total: 0, has_more: false, limit: 50, offset: 0, items: [] }
  })

  await getCostStats({ campaignId: 'camp-1', windowDays: 30, limit: 25, offset: 10 })
  assert.match(requested, /campaign_id=camp-1/)
  assert.match(requested, /window_days=30/)
  assert.match(requested, /limit=25/)
  assert.match(requested, /offset=10/)
})

test('export URL builders include campaign scope', () => {
  const companyUrl = getCompaniesExportUrl('camp-1')
  const contactsUrl = getContactsExportUrl({ campaignId: 'camp-1', companyId: 'co-1' })
  assert.match(companyUrl, /campaign_id=camp-1/)
  assert.match(contactsUrl, /campaign_id=camp-1/)
  assert.match(contactsUrl, /company_id=co-1/)
})

test('verifyContacts posts campaign-scoped payload', async () => {
  let sentBody = ''
  mockFetch((_url, init) => {
    sentBody = String(init?.body ?? '')
    return { job_id: 'j1', selected_count: 2, message: 'Queued ZeroBounce verification for 2 contacts.' }
  })

  await verifyContacts({ campaign_id: 'camp-1', contact_ids: ['c1', 'c2'] })
  assert.match(sentBody, /"campaign_id":"camp-1"/)
  assert.match(sentBody, /"contact_ids":\["c1","c2"\]/)
})

test('previewTitleRuleImpact serializes campaign_id', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return {
      campaign_id: 'camp-1',
      source: 'snov',
      include_stale: false,
      stale_days: 30,
      stale_days_override: null,
      provider_default_days: { snov: 30, apollo: 45 },
      force_refresh: false,
      affected_company_count: 0,
      affected_contact_count: 0,
      stale_contact_count: 0,
      affected_company_ids: [],
    }
  })

  await previewTitleRuleImpact('camp-1')
  assert.match(requested, /\/v1\/title-match-rules\/impact-preview\?campaign_id=camp-1$/)
})

test('queueTitleRuleImpactFetch serializes campaign_id and source', async () => {
  let requested = ''
  let method = ''
  mockFetch((url, init) => {
    requested = url
    method = String(init?.method ?? '')
    return { requested_count: 0, queued_count: 0, already_fetching_count: 0, queued_job_ids: [] }
  })

  await queueTitleRuleImpactFetch('camp-1', 'apollo')
  assert.match(requested, /\/v1\/title-match-rules\/impact-fetch\?campaign_id=camp-1&source=apollo$/)
  assert.equal(method, 'POST')
})

test('title-rule impact endpoints serialize stale options', async () => {
  const requested: string[] = []
  mockFetch((url, init) => {
    requested.push(url)
    return init?.method === 'POST'
      ? { requested_count: 0, queued_count: 0, already_fetching_count: 0, queued_job_ids: [] }
      : {
          campaign_id: 'camp-1',
          source: 'both',
          include_stale: true,
          stale_days: 45,
          stale_days_override: 45,
          provider_default_days: { snov: 30, apollo: 45 },
          force_refresh: false,
          affected_company_count: 0,
          affected_contact_count: 0,
          stale_contact_count: 0,
          affected_company_ids: [],
        }
  })

  await previewTitleRuleImpact('camp-1', { includeStale: true, staleDays: 45 })
  await queueTitleRuleImpactFetch('camp-1', 'both', { includeStale: true, staleDays: 45 })

  assert.match(requested[0], /include_stale=true/)
  assert.match(requested[0], /stale_days=45/)
  assert.match(requested[1], /source=both/)
  assert.match(requested[1], /include_stale=true/)
  assert.match(requested[1], /stale_days=45/)
})

test('title-rule impact endpoints serialize force_refresh option', async () => {
  const requested: string[] = []
  mockFetch((url, init) => {
    requested.push(url)
    return init?.method === 'POST'
      ? { requested_count: 0, queued_count: 0, already_fetching_count: 0, queued_job_ids: [] }
      : {
          campaign_id: 'camp-1',
          source: 'snov',
          include_stale: false,
          stale_days: 30,
          stale_days_override: null,
          provider_default_days: { snov: 30, apollo: 45 },
          force_refresh: true,
          affected_company_count: 0,
          affected_contact_count: 0,
          stale_contact_count: 0,
          affected_company_ids: [],
        }
  })

  await previewTitleRuleImpact('camp-1', { forceRefresh: true })
  await queueTitleRuleImpactFetch('camp-1', 'snov', { forceRefresh: true })

  assert.match(requested[0], /force_refresh=true/)
  assert.match(requested[1], /force_refresh=true/)
})

test('previewTitleRuleImpact serializes source option', async () => {
  let requested = ''
  mockFetch((url) => {
    requested = url
    return {
      campaign_id: 'camp-1',
      source: 'apollo',
      include_stale: true,
      stale_days: 45,
      stale_days_override: null,
      provider_default_days: { snov: 30, apollo: 45 },
      force_refresh: false,
      affected_company_count: 0,
      affected_contact_count: 0,
      stale_contact_count: 0,
      affected_company_ids: [],
    }
  })

  await previewTitleRuleImpact('camp-1', { source: 'apollo', includeStale: true })
  assert.match(requested, /source=apollo/)
  assert.match(requested, /include_stale=true/)
})
