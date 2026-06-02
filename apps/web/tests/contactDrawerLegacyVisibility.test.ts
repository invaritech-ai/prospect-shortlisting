import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('contact drawer loads email contacts first and paginates no-email contacts', () => {
  const source = readFileSync(new URL('../src/components/views/contacts/ContactDrawer.tsx', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/lib/api.ts', import.meta.url), 'utf8')
  const types = readFileSync(new URL('../src/lib/types.ts', import.meta.url), 'utf8')

  assert.match(source, /hasEmail:\s*true/)
  assert.match(source, /hasEmail:\s*false/)
  assert.match(source, /Load more/)
  assert.match(source, /Qualified contacts/)
  assert.match(source, /Fetched people not used/)
  assert.match(source, /listFetchedPeople/)
  assert.match(api, /export async function listFetchedPeople/)
  assert.match(types, /export type FetchedPersonRead/)
  assert.doesNotMatch(source, /provider_evidence_json/)
})
