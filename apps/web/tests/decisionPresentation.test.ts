import test from 'node:test'
import assert from 'node:assert/strict'

import { getDecisionDisplay } from '../src/lib/decisionPresentation.ts'

test('shows a manual decision with a manual confidence marker', () => {
  const display = getDecisionDisplay({
    feedback_manual_label: 'crap',
    latest_decision: 'possible',
    latest_confidence: 0.92,
  })

  assert.deepEqual(display, {
    badgeLabel: '✏ crap',
    badgeValue: 'crap',
    confidenceLabel: 'Manual',
    isManual: true,
  })
})

test('falls back to the ai decision and confidence when no manual override exists', () => {
  const display = getDecisionDisplay({
    feedback_manual_label: null,
    latest_decision: 'possible',
    latest_confidence: 0.876,
  })

  assert.deepEqual(display, {
    badgeLabel: 'possible',
    badgeValue: 'possible',
    confidenceLabel: '88%',
    isManual: false,
  })
})

test('shows empty placeholders when there is no decision', () => {
  const display = getDecisionDisplay({
    feedback_manual_label: null,
    latest_decision: null,
    latest_confidence: null,
  })

  assert.deepEqual(display, {
    badgeLabel: null,
    badgeValue: null,
    confidenceLabel: '—',
    isManual: false,
  })
})
