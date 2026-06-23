import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

function readSource(path: string): string {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

function testPath(path: string): string {
  return fileURLToPath(new URL(path, import.meta.url))
}

test('production mock-data fallback modules are removed', () => {
  assert.equal(existsSync(testPath('../src/lib/mockData.ts')), false)
  assert.equal(existsSync(testPath('../src/lib/useAppData.ts')), false)
})

test('obsolete validation and reveal frontend types are removed', () => {
  const types = readSource('src/lib/types.ts')

  for (const obsoleteType of [
    'S4VerifFilter',
    'ContactVerifyRequest',
    'ContactVerifyResult',
    'DiscoveredContactRead',
    'DiscoveredContactCountsResponse',
    'ContactRevealRequest',
    'ContactRevealResult',
  ]) {
    assert.doesNotMatch(types, new RegExp(`\\b${obsoleteType}\\b`))
  }

  assert.match(types, /stage:\s*'s1'\s*\|\s*'s2'\s*\|\s*'s3'\s*\|\s*'s4'/)
  assert.doesNotMatch(types, /stage:\s*'s1'\s*\|\s*'s2'\s*\|\s*'s3'\s*\|\s*'s5'/)
})

test('pipeline mapping no longer exposes standalone verification filters', () => {
  const pipelineMappings = readSource('src/lib/pipelineMappings.ts')

  assert.doesNotMatch(pipelineMappings, /\bverifFilterToParams\b/)
  assert.doesNotMatch(pipelineMappings, /\bS4VerifFilter\b/)
})

test('queue history UI is removed until the backend exists', () => {
  assert.equal(existsSync(testPath('../src/components/views/QueueHistoryView.tsx')), false)
})

test('standalone reveal view test is deleted and validation comment is current', () => {
  assert.equal(existsSync(testPath('s4RevealView.test.tsx')), false)

  const globals = readSource('src/globals.css')
  assert.doesNotMatch(globals, /S5 · Validation/)
})
