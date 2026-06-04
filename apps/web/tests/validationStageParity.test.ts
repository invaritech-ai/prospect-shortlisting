import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('S4 validation view follows S1-S3 table conventions with real backend data', () => {
  const source = readFileSync(new URL('../src/components/views/validation/ValidationView.tsx', import.meta.url), 'utf8')

  assert.match(source, /const PAGE_SIZE = 50/)
  assert.match(source, /const MAX_VERIFICATION_BATCH_SIZE = 200/)
  assert.match(source, /const LETTERS = \['#'/)
  assert.match(source, /listEmailVerificationContacts/)
  assert.match(source, /listEmailVerificationContactIds/)
  assert.match(source, /getEmailVerificationLetterCounts/)
  assert.match(source, /previewEmailVerification/)
  assert.match(source, /createEmailVerificationBatch/)
  assert.match(source, /downloadFreshValidEmailCsv/)
  assert.match(source, /Company A-Z/)
  assert.match(source, /Download valid emails/)
  assert.match(source, /Validate first/)
  assert.match(source, /Select all/)
  assert.match(source, /← Prev/)
  assert.match(source, /Next →/)
  assert.doesNotMatch(source, /MOCK_VALIDATION_ROWS/)
  assert.doesNotMatch(source, /MOCK_VALIDATION_STATS/)
  assert.doesNotMatch(source, /ValidationSettingsDrawer/)
})
