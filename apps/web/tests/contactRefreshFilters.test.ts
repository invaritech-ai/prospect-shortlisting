import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('contacts refresh ignores stale row and letter-count responses after filter changes', () => {
  const source = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')

  assert.match(source, /useRef/)
  assert.match(source, /createQueryRequestGate/)
  assert.match(source, /rowsQueryKey/)
  assert.match(source, /letterCountsQueryKey/)
  assert.match(source, /rowsRequestGate\.isCurrent/)
  assert.match(source, /letterCountsRequestGate\.isCurrent/)
  assert.doesNotMatch(source, /requestSeq !== rowsRequestSeq\.current/)
})
