import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const projectRoot = process.cwd()

function readSource(path: string): string {
  return readFileSync(join(projectRoot, 'apps/web', path), 'utf8')
}

test('obsolete validation mocks are removed from mock data exports', () => {
  const mockData = readSource('src/lib/mockData.ts')
  const appData = readSource('src/lib/useAppData.ts')

  for (const source of [mockData, appData]) {
    assert.doesNotMatch(source, /\bMOCK_VALIDATION_ROWS\b/)
    assert.doesNotMatch(source, /\bMOCK_VALIDATION_STATS\b/)
    assert.doesNotMatch(source, /\bMockValidationRow\b/)
  }
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

test('queue history uses S4 as the validation queue stage', () => {
  const queueHistory = readSource('src/components/views/QueueHistoryView.tsx')

  assert.match(queueHistory, /type StageFilter = 'all' \| 's1' \| 's2' \| 's3' \| 's4'/)
  assert.match(queueHistory, /s4:\s*'S4 · Verify'/)
  assert.doesNotMatch(queueHistory, /s5:\s*'S4/)
})

test('standalone reveal view test is deleted and validation comment is current', () => {
  assert.equal(existsSync(join(projectRoot, 'apps/web/tests/s4RevealView.test.tsx')), false)

  const globals = readSource('src/globals.css')
  assert.doesNotMatch(globals, /S5 · Validation/)
})
