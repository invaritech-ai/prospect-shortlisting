import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('contacts header uses possible-scope API totals instead of loaded page rows', () => {
  const source = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')

  assert.match(source, /value:\s*counts\.contacts_found/)
  assert.match(source, /value:\s*counts\.emails_found/)
  assert.match(source, /value:\s*counts\.fetched_people_found/)
  assert.doesNotMatch(source, /rows\.reduce\(\(sum,\s*row\)\s*=>\s*sum\s*\+\s*row\.contacts_found/)
  assert.doesNotMatch(source, /rows\.reduce\(\(sum,\s*row\)\s*=>\s*sum\s*\+\s*row\.emails_found/)
})

test('contacts view warns when a running batch uses an older criteria snapshot', () => {
  const source = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')

  assert.match(source, /activeBatchCriteriaChanged/)
  assert.match(source, /Fetch running with rules from/)
  assert.match(source, /New title rules apply to future fetches/)
})
