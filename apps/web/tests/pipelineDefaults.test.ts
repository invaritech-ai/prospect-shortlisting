import test from 'node:test'
import assert from 'node:assert/strict'

import { getDefaultPipelineScrapeSubFilter } from '../src/lib/pipelineDefaults.ts'

test('defaults S1 scraping to all instead of pending', () => {
  assert.equal(getDefaultPipelineScrapeSubFilter('s1-scraping'), 'all')
})

test('keeps the same all default for the other company pipeline views', () => {
  assert.equal(getDefaultPipelineScrapeSubFilter('s2-ai'), 'all')
  assert.equal(getDefaultPipelineScrapeSubFilter('s3-contacts'), 'all')
})
