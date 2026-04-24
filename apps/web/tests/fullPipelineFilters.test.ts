import test from 'node:test'
import assert from 'node:assert/strict'

import {
  companyListBrowseUrl,
} from '../src/lib/fullPipelineFilters.ts'
import type { CompanyListItem } from '../src/lib/types.ts'

function row(partial: Partial<CompanyListItem>): CompanyListItem {
  return {
    id: '1',
    upload_id: 'u',
    upload_filename: 'f',
    raw_url: '',
    normalized_url: '',
    domain: 'example.com',
    pipeline_stage: 'uploaded',
    created_at: '2026-01-01T00:00:00Z',
    last_activity: '2026-01-01T00:00:00Z',
    latest_decision: null,
    latest_confidence: null,
    latest_scrape_job_id: null,
    latest_scrape_status: null,
    latest_scrape_terminal: null,
    latest_analysis_run_id: null,
    latest_analysis_job_id: null,
    latest_analysis_status: null,
    latest_analysis_terminal: null,
    feedback_thumbs: null,
    feedback_comment: null,
    feedback_manual_label: null,
    latest_scrape_error_code: null,
    contact_count: 0,
    discovered_contact_count: 0,
    discovered_title_matched_count: 0,
    revealed_contact_count: 0,
    contact_fetch_status: null,
    ...partial,
  }
}

test('companyListBrowseUrl falls back to https domain', () => {
  assert.equal(companyListBrowseUrl(row({ domain: 'x.com', raw_url: '', normalized_url: '' })), 'https://x.com')
  assert.equal(
    companyListBrowseUrl(row({ domain: 'x.com', raw_url: '', normalized_url: 'https://x.com/' })),
    'https://x.com/',
  )
})
