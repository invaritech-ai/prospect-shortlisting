import test from 'node:test'
import assert from 'node:assert/strict'

import { getDisplayedScrapeFailedCount } from '../src/lib/scrapeCounts.ts'

test('displayed scrape failed count does not double-count permanent failures', () => {
  assert.equal(
    getDisplayedScrapeFailedCount({
      scrape_failed: 4,
      scrape_soft_fail: 4,
      scrape_permanent_fail: 2,
    }),
    4,
  )
})

test('displayed scrape failed count falls back to mutually-exclusive pieces', () => {
  assert.equal(
    getDisplayedScrapeFailedCount({
      scrape_soft_fail: 2,
      scrape_permanent_fail: 2,
    }),
    4,
  )
})
