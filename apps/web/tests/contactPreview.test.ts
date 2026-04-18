import test from 'node:test'
import assert from 'node:assert/strict'

import {
  isContactVerificationEligible,
  summarizeCompanyContacts,
} from '../src/lib/contactPreview.ts'
import type { ProspectContactRead } from '../src/lib/types.ts'

function makeContact(overrides: Partial<ProspectContactRead> = {}): ProspectContactRead {
  return {
    id: overrides.id ?? 'contact-1',
    company_id: overrides.company_id ?? 'company-1',
    contact_fetch_job_id: overrides.contact_fetch_job_id ?? 'fetch-1',
    domain: overrides.domain ?? 'example.com',
    source: overrides.source ?? 'snov',
    first_name: overrides.first_name ?? 'Ada',
    last_name: overrides.last_name ?? 'Lovelace',
    title: overrides.title ?? 'Director of Marketing',
    title_match: overrides.title_match ?? false,
    linkedin_url: overrides.linkedin_url ?? null,
    email: overrides.email ?? null,
    pipeline_stage: overrides.pipeline_stage ?? 'fetched',
    provider_email_status: overrides.provider_email_status ?? null,
    verification_status: overrides.verification_status ?? 'unverified',
    snov_confidence: overrides.snov_confidence ?? null,
    created_at: overrides.created_at ?? '2026-04-18T00:00:00',
    updated_at: overrides.updated_at ?? '2026-04-18T00:00:00',
  }
}

test('requires title match, email, and unverified status for verify eligibility', () => {
  assert.equal(isContactVerificationEligible(makeContact({
    title_match: true,
    email: 'ada@example.com',
    verification_status: 'unverified',
  })), true)

  assert.equal(isContactVerificationEligible(makeContact({
    title_match: false,
    email: 'ada@example.com',
    verification_status: 'unverified',
  })), false)

  assert.equal(isContactVerificationEligible(makeContact({
    title_match: true,
    email: null,
    verification_status: 'unverified',
  })), false)

  assert.equal(isContactVerificationEligible(makeContact({
    title_match: true,
    email: 'ada@example.com',
    verification_status: 'valid',
  })), false)
})

test('summarizes fetched, matched, email, verified, ready, and eligible counts from contacts', () => {
  const contacts = [
    makeContact({ id: 'a', title_match: true, email: 'a@example.com', verification_status: 'unverified', pipeline_stage: 'fetched' }),
    makeContact({ id: 'b', title_match: true, email: 'b@example.com', verification_status: 'valid', pipeline_stage: 'verified' }),
    makeContact({ id: 'c', title_match: false, email: 'c@example.com', verification_status: 'unverified', pipeline_stage: 'fetched' }),
    makeContact({ id: 'd', title_match: true, email: 'd@example.com', verification_status: 'valid', pipeline_stage: 'campaign_ready' }),
    makeContact({ id: 'e', title_match: true, email: null, verification_status: 'unverified', pipeline_stage: 'fetched' }),
  ]

  assert.deepEqual(summarizeCompanyContacts(contacts), {
    total: 5,
    matched: 4,
    withEmail: 4,
    verified: 1,
    campaignReady: 1,
    eligibleToVerify: 1,
  })
})
