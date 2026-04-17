import test from 'node:test'
import assert from 'node:assert/strict'

import { getPipelineCompanyQuery } from '../src/lib/pipelineQuery.ts'

test('S2 AI view preserves the selected decision filter', () => {
  assert.deepEqual(getPipelineCompanyQuery('s2-ai', 'possible'), {
    stageFilter: 'has_scrape',
    decisionFilter: 'possible',
  })
})

test('non-AI pipeline views always use the all decision filter', () => {
  assert.deepEqual(getPipelineCompanyQuery('s1-scraping', 'possible'), {
    stageFilter: 'all',
    decisionFilter: 'all',
  })
})

test('S3 contact fetch uses all companies and preserves the decision filter', () => {
  assert.deepEqual(getPipelineCompanyQuery('s3-contacts', 'crap'), {
    stageFilter: 'all',
    decisionFilter: 'crap',
  })
  assert.deepEqual(getPipelineCompanyQuery('s3-contacts', 'possible'), {
    stageFilter: 'all',
    decisionFilter: 'possible',
  })
})
