import test from 'node:test'
import assert from 'node:assert/strict'
import { createQueryRequestGate } from '../src/lib/requestGate.ts'

test('query request gate rejects stale responses from an old filter', () => {
  const gate = createQueryRequestGate()

  const oldFilterPoll = gate.start('status=running&page=0')
  const currentFilterLoad = gate.start('status=all&page=0')

  assert.equal(gate.isCurrent(oldFilterPoll, 'status=all&page=0'), false)
  assert.equal(gate.isCurrent(currentFilterLoad, 'status=all&page=0'), true)
})

test('query request gate lets a newer refresh for the same filter own the response', () => {
  const gate = createQueryRequestGate()

  const foregroundLoad = gate.start('status=all&page=0')
  const quietRefresh = gate.start('status=all&page=0')

  assert.equal(gate.isCurrent(foregroundLoad, 'status=all&page=0'), false)
  assert.equal(gate.isCurrent(quietRefresh, 'status=all&page=0'), true)
})
