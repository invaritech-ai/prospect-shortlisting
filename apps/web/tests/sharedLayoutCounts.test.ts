import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const SHARED_LAYOUT_FILES = [
  'src/components/layout/Sidebar.tsx',
  'src/components/layout/BottomNav.tsx',
  'src/components/layout/header/LiveStatus.tsx',
]

test('shared layout count components do not import mock data fallbacks', () => {
  for (const file of SHARED_LAYOUT_FILES) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /MOCK_STATS|MOCK_COMPANY_COUNTS|mockData|useAppData/)
  }
})
