import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const tableFiles = [
  '../src/components/views/scraping/ScrapingTable.tsx',
  '../src/components/views/ai-review/AIReviewTable.tsx',
  '../src/components/views/contacts/ContactsTable.tsx',
  '../src/components/views/validation/ValidationTable.tsx',
]

test('S1-S4 stage tables use sortable headers for data columns only', () => {
  const [scraping, aiReview, contacts, validation] = tableFiles.map((path) =>
    readFileSync(new URL(path, import.meta.url), 'utf8'),
  )

  for (const source of [scraping, aiReview, contacts, validation]) {
    assert.match(source, /SortableHeader/)
    assert.match(source, /sortBy/)
    assert.match(source, /sortDir/)
    assert.match(source, /onSort/)
  }

  assert.match(scraping, /field="domain"/)
  assert.match(scraping, /field="status"/)
  assert.match(scraping, /field="updated"/)
  assert.doesNotMatch(scraping, /field="action"/)

  assert.match(aiReview, /field="domain"/)
  assert.match(aiReview, /field="verdict"/)
  assert.match(aiReview, /field="confidence"/)
  assert.match(aiReview, /field="pages"/)
  assert.match(aiReview, /field="reviewed"/)
  assert.doesNotMatch(aiReview, /field="reasoning"/)
  assert.doesNotMatch(aiReview, /field="override"/)

  assert.match(contacts, /field="domain"/)
  assert.match(contacts, /field="status"/)
  assert.match(contacts, /field="fetched"/)
  assert.match(contacts, /field="contacts"/)
  assert.match(contacts, /field="emails"/)
  assert.match(contacts, /field="updated"/)
  assert.doesNotMatch(contacts, /field="action"/)

  assert.match(validation, /field="contact"/)
  assert.match(validation, /field="company"/)
  assert.match(validation, /field="email"/)
  assert.match(validation, /field="status"/)
  assert.match(validation, /field="verified"/)
  assert.doesNotMatch(validation, /field="action"/)
})
