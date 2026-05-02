import test from 'node:test'
import assert from 'node:assert/strict'
import { renderToStaticMarkup } from 'react-dom/server'

import { S4RevealView } from '../src/components/views/pipeline/S4RevealView.tsx'
import type { DiscoveredContactCountsResponse } from '../src/lib/types.ts'

const noop = () => {}

test('S4 reveal counts tolerate missing already_revealed from production API payloads', () => {
  const counts = {
    total: 12,
    matched: 8,
    fresh: 7,
    stale: 5,
  } as unknown as DiscoveredContactCountsResponse

  const html = renderToStaticMarkup(
    <S4RevealView
      contacts={{ total: 0, has_more: false, limit: 25, offset: 0, items: [] }}
      counts={counts}
      letterCounts={{}}
      activeLetters={new Set()}
      selectedIds={[]}
      matchFilter="all"
      search=""
      isSelectingAll={false}
      sortBy="last_seen_at"
      sortDir="desc"
      onMatchFilterChange={noop}
      onSearchChange={noop}
      onToggleLetter={noop}
      onClearLetters={noop}
      onToggle={noop}
      onToggleAll={noop}
      staleEmailOnly={false}
      onStaleEmailOnlyChange={noop}
      onSelectAllMatching={noop}
      onClearSelection={noop}
      onRevealSelected={noop}
      onOpenTitleRules={noop}
      offset={0}
      pageSize={25}
      onPagePrev={noop}
      onPageNext={noop}
      onPageSizeChange={noop}
      onSort={noop}
      isLoading={false}
      isRevealing={false}
    />,
  )

  assert.match(html, />0<\/span><span class="ml-1.5"/)
})
