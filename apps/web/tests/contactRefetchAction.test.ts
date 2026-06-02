import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('contacts stage exposes explicit refetch mode for completed selected rows', () => {
  const view = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')
  const table = readFileSync(new URL('../src/components/views/contacts/ContactsTable.tsx', import.meta.url), 'utf8')
  const cards = readFileSync(new URL('../src/components/views/contacts/ContactsCards.tsx', import.meta.url), 'utf8')
  const types = readFileSync(new URL('../src/lib/types.ts', import.meta.url), 'utf8')

  assert.match(types, /export type EmailFetchMode = 'fetch' \| 'refetch'/)
  assert.match(view, /function canRefetch\(row: EmailFetchCompanyRow\): boolean/)
  assert.match(view, /setPreviewMode\(mode\)/)
  assert.match(view, /previewEmailFetch\(\{ campaign_id: campaignId, domain_ids: uniqueIds, mode \}\)/)
  assert.match(view, /createEmailFetchBatch\(\{ campaign_id: campaignId, domain_ids: previewDomainIds, mode: previewMode \}\)/)
  assert.match(view, /Refetch \$\{selectedRefetchIds\.length\}/)
  assert.match(table, /onRefetch/)
  assert.match(table, /Refetch/)
  assert.match(cards, /onRefetch/)
  assert.match(cards, /Refetch/)
})

test('contact preview copy distinguishes Apollo estimates from Snov fallback estimates', () => {
  const dialog = readFileSync(new URL('../src/components/views/contacts/EmailFetchPreviewDialog.tsx', import.meta.url), 'utf8')

  assert.match(dialog, /Apollo reveals/)
  assert.match(dialog, /Snov discovery searches/)
  assert.match(dialog, /Snov email lookups/)
  assert.match(dialog, /Estimated paid usage/)
  assert.match(dialog, /Run fetch/)
  assert.match(dialog, /Apollo found no title matches in preview/)
  assert.match(dialog, /may use provider credits again/)
  assert.doesNotMatch(dialog, /Fallback fills/)
  assert.doesNotMatch(dialog, /Snov fallback needed/)
  assert.doesNotMatch(dialog, /No title-matched preview candidates/)
})
