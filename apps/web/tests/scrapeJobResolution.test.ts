import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveScrapeJobRead } from '../src/lib/scrapeJobResolution.ts'
import type { ScrapeJobRead } from '../src/lib/types.ts'

const FULL_JOB: ScrapeJobRead = {
  id: 'job-1',
  website_url: 'https://example.com',
  normalized_url: 'https://example.com',
  domain: 'example.com',
  status: 'completed',
  terminal_state: true,
  js_fallback: false,
  include_sitemap: false,
  general_model: 'gpt',
  classify_model: 'gpt',
  discovered_urls_count: 3,
  pages_fetched_count: 3,
  fetch_failures_count: 0,
  markdown_pages_count: 2,
  llm_used_count: 0,
  llm_failed_count: 0,
  last_error_code: null,
  last_error_message: null,
  created_at: '2026-04-17T00:00:00',
  updated_at: '2026-04-17T00:01:00',
  started_at: '2026-04-17T00:00:05',
  finished_at: '2026-04-17T00:00:30',
}

test('returns the original scrape job when it already has panel fields', async () => {
  let fetchCalls = 0
  const resolved = await resolveScrapeJobRead(FULL_JOB, async () => {
    fetchCalls += 1
    return FULL_JOB
  })

  assert.equal(fetchCalls, 0)
  assert.equal(resolved, FULL_JOB)
})

test('fetches the full scrape job when only a partial shell is available', async () => {
  const partial = { id: 'job-1' } as ScrapeJobRead

  let fetchCalls = 0
  const resolved = await resolveScrapeJobRead(partial, async (jobId) => {
    fetchCalls += 1
    assert.equal(jobId, 'job-1')
    return FULL_JOB
  })

  assert.equal(fetchCalls, 1)
  assert.deepEqual(resolved, FULL_JOB)
})
