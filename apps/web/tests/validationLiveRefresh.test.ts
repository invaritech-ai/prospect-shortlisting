import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('S4 validation view refreshes from campaign events and active batch polling', () => {
  const source = readFileSync(new URL('../src/components/views/validation/ValidationView.tsx', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/lib/api.ts', import.meta.url), 'utf8')

  assert.match(source, /useCampaignEventStream/)
  assert.match(source, /event\.stage === 's4'/)
  assert.match(source, /getActiveEmailVerificationBatch/)
  assert.match(source, /POLL_STATUS_ACTIVE_MS/)
  assert.match(source, /POLL_HEAVY_ACTIVE_MS/)
  assert.match(source, /statusPollBusyRef/)
  assert.match(source, /heavyPollBusyRef/)
  assert.doesNotMatch(source, /setInterval/)
  assert.match(api, /\/v1\/email-verification\/batches\/active/)
})
