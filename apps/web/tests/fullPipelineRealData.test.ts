import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('full pipeline is company-first and uses one optimized backend endpoint', () => {
  const view = readFileSync(new URL('../src/components/views/pipeline/FullPipelineView.tsx', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

  assert.match(view, /campaignId/)
  assert.match(view, /stageCounts/)
  assert.match(view, /listFullPipelineCompanies/)
  assert.match(view, /validCount/)
  assert.match(view, /contactsFound/)
  assert.match(view, /valid_email_count/)
  assert.match(view, /contacts_found/)
  assert.match(view, /emailTotal/)
  assert.match(view, /email_contact_count/)
  assert.match(view, /S4 valid \/ emails/)
  assert.doesNotMatch(view, /\$\{validCount\.toLocaleString\(\)\}\s*\/\s*\$\{contactsFound\.toLocaleString\(\)\}/)
  assert.doesNotMatch(view, /listDomains/)
  assert.doesNotMatch(view, /listContacts/)
  assert.doesNotMatch(view, /fetchVisibleDomainSummaries/)
  assert.doesNotMatch(view, /Promise\.all/)
  assert.doesNotMatch(view, /fetchAllContactSummaries/)
  assert.doesNotMatch(view, /fetchAllValidationSummaries/)
  assert.doesNotMatch(view, /for\s*\(\s*;\s*;\s*\)/)
  assert.doesNotMatch(view, /MOCK_FULL_PIPELINE_COMPANIES/)
  assert.match(app, /<FullPipelineView\s+campaignId=\{selectedCampaignId\}/)
})
