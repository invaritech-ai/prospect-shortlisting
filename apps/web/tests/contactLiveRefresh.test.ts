import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('contacts stage refreshes from campaign events and S1-style fallback ticks', () => {
  const source = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/lib/api.ts', import.meta.url), 'utf8')

  assert.match(source, /useCampaignEventStream/)
  assert.match(source, /getActiveEmailFetchBatch/)
  assert.match(source, /event\.stage === 's3'/)
  assert.match(source, /POLL_STATUS_ACTIVE_MS/)
  assert.match(source, /POLL_HEAVY_ACTIVE_MS/)
  assert.match(source, /statusPollBusyRef/)
  assert.match(source, /heavyPollBusyRef/)
  assert.match(source, /runStatusTick/)
  assert.match(source, /runHeavyTick/)
  assert.doesNotMatch(source, /setInterval/)
  assert.match(api, /getActiveEmailFetchBatch/)
  assert.match(api, /\/v1\/email-fetch\/batches\/active/)
})

test('contacts stage reports active email fetch batches to the app shell', () => {
  const view = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

  assert.match(view, /onActiveBatchChange\?: \(batch: EmailFetchBatchRead \| null\) => void/)
  assert.match(view, /onActiveBatchChange\?\.\(activeBatch\)/)
  assert.match(view, /onActiveBatchChange\?\.\(null\)/)
  assert.match(app, /activeEmailFetchBatch/)
  assert.match(app, /wasEmailFetchLiveRef/)
  assert.match(app, /onActiveBatchChange=\{setActiveEmailFetchBatch\}/)
})

test('app shell does not synthesize contacts live counts from email fetch batch counters', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

  assert.doesNotMatch(app, /stageCountsWithEmailFetchBatch/)
  assert.match(app, /stageCounts=\{stageCounts\}/)
})

test('contacts page live stat follows backend running count, not local batch presence', () => {
  const view = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')

  assert.match(view, /live:\s*counts\.running > 0/)
  assert.doesNotMatch(view, /live:\s*counts\.running > 0 \|\| Boolean\(activeBatch\)/)
})

test('unfiltered contacts API counts are mirrored into shell counts immediately', () => {
  const view = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

  assert.match(view, /onContactCountsChange\?: \(counts: EmailFetchCompanyCounts \| null\) => void/)
  assert.match(view, /filter === 'all' && letterFilter === 'all' && !normalizedSearch/)
  assert.match(view, /onContactCountsChange\?\.\(res\.counts\)/)
  assert.match(app, /mergeContactCountsIntoStageCounts/)
  assert.match(app, /badge:\s*counts\.pending \+ counts\.running \+ counts\.failed \+ counts\.no_match/)
  assert.match(app, /onContactCountsChange=\{mergeContactCountsIntoStageCounts\}/)
})
