import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('contacts stage uses S1/S2-style pagination, letter chips, and server-side matching selection', () => {
  const source = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')

  assert.match(source, /const PAGE_SIZE = 50/)
  assert.match(source, /const LETTERS = \['#'/)
  assert.match(source, /getEmailFetchLetterCounts/)
  assert.match(source, /listEmailFetchCompanyIds/)
  assert.match(source, /offset:\s*page \* PAGE_SIZE/)
  assert.match(source, /Select first/)
  assert.match(source, /Select all/)
  assert.match(source, /← Prev/)
  assert.match(source, /Next →/)
  assert.doesNotMatch(source, /Fetch \$\{fetchableVisibleIds\.length\} pending/)
})
