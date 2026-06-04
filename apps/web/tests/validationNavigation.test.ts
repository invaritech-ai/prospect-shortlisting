import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('validation is product S4 and old reveal/S5 routes are removed', () => {
  const navigation = readFileSync(new URL('../src/lib/navigation.ts', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const dashboard = readFileSync(new URL('../src/components/views/pipeline/DashboardView.tsx', import.meta.url), 'utf8')

  assert.match(navigation, /'s4-validation'/)
  assert.doesNotMatch(navigation, /'s4-reveal'/)
  assert.doesNotMatch(navigation, /'s5-validation'/)
  assert.match(app, /activeView === 's4-validation'/)
  assert.doesNotMatch(app, /S4 · Reveal/)
  assert.match(dashboard, /stageNum:\s*'S4'/)
  assert.match(dashboard, /Email Verification|Validation/)
})

test('email verification row type matches the backend public row schema', () => {
  const types = readFileSync(new URL('../src/lib/types.ts', import.meta.url), 'utf8')
  const rowMatch = types.match(/export type EmailVerificationContactRow = \{(?<body>[\s\S]*?)\n\}/)
  assert.ok(rowMatch?.groups?.body, 'EmailVerificationContactRow type should exist')

  const rowBody = rowMatch.groups.body
  assert.match(rowBody, /contact_id: string/)
  assert.match(rowBody, /selected_email: string/)
  assert.match(rowBody, /status: EmailVerificationStatus/)
  assert.doesNotMatch(rowBody, /raw_status/)
  assert.doesNotMatch(rowBody, /sub_status/)
})
