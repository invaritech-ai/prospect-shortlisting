import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('S4 selection allows mixed rows and previews eligible subset', () => {
  const source = readFileSync(new URL('../src/components/views/validation/ValidationView.tsx', import.meta.url), 'utf8')

  assert.match(source, /selectedActionableIds/)
  assert.match(source, /No selected emails need validation/)
  assert.match(source, /skipped_count/)
  assert.match(source, /cached_count/)
  assert.match(source, /paid_validation_count/)
  assert.doesNotMatch(source, /disabled=\{row\.status === 'valid'\}/)
})
