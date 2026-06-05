import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('campaign cards use real validation counts from campaign payload', () => {
  const view = readFileSync(new URL('../src/components/views/campaigns/CampaignsView.tsx', import.meta.url), 'utf8')
  const types = readFileSync(new URL('../src/lib/types.ts', import.meta.url), 'utf8')

  assert.match(types, /valid_email_count: number/)
  assert.match(view, /validEmails: c\.valid_email_count/)
  assert.doesNotMatch(view, /validEmails:\s*0/)
})
