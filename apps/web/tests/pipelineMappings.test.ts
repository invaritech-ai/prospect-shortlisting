import test from 'node:test'
import assert from 'node:assert/strict'

import {
  getResumeStageForCompany,
  scrapeSubToFilter,
} from '../src/lib/pipelineMappings.ts'

test('resume stage favors earliest failed stage', () => {
  assert.equal(
    getResumeStageForCompany({
      latest_scrape_status: 'site_unavailable',
      latest_analysis_status: 'failed',
      contact_fetch_status: 'failed',
    }),
    'S1',
  )
  assert.equal(
    getResumeStageForCompany({
      latest_scrape_status: 'completed',
      latest_analysis_status: 'dead',
      contact_fetch_status: 'failed',
    }),
    'S2',
  )
  assert.equal(
    getResumeStageForCompany({
      latest_scrape_status: 'completed',
      latest_analysis_status: 'succeeded',
      contact_fetch_status: 'failed',
    }),
    'S3',
  )
  assert.equal(
    getResumeStageForCompany({
      latest_scrape_status: 'completed',
      latest_analysis_status: 'succeeded',
      contact_fetch_status: 'succeeded',
    }),
    null,
  )
})

test('scrape sub-filter mapping stays explicit', () => {
  assert.equal(scrapeSubToFilter('pending'), 'not-started')
  assert.equal(scrapeSubToFilter('not-started'), 'not-started')
  assert.equal(scrapeSubToFilter('active'), 'in-progress')
  assert.equal(scrapeSubToFilter('in-progress'), 'in-progress')
  assert.equal(scrapeSubToFilter('done'), 'done')
  assert.equal(scrapeSubToFilter('cancelled'), 'cancelled')
  assert.equal(scrapeSubToFilter('permanent'), 'permanent')
  assert.equal(scrapeSubToFilter('failed'), 'soft')
  assert.equal(scrapeSubToFilter('soft'), 'soft')
  assert.equal(scrapeSubToFilter('all'), 'all')
})
