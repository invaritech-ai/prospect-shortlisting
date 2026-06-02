import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('provider health remains dashboard-owned and is not rendered inside S3', () => {
  const contactsView = readFileSync(new URL('../src/components/views/contacts/ContactsView.tsx', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const dashboardView = readFileSync(new URL('../src/components/views/pipeline/DashboardView.tsx', import.meta.url), 'utf8')
  const servicesHealth = readFileSync(new URL('../src/components/views/dashboard/ServicesHealth.tsx', import.meta.url), 'utf8')

  assert.doesNotMatch(contactsView, /ContactProviderStatus/)
  assert.doesNotMatch(contactsView, /servicesHealth/)
  assert.doesNotMatch(app, /onRefreshProviderHealth/)
  assert.match(dashboardView, /ServicesHealth/)
  assert.match(servicesHealth, /apollo/)
  assert.match(servicesHealth, /snov/)
  assert.match(servicesHealth, /credits_remaining/)
})
