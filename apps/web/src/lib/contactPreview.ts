import type { ProspectContactRead } from './types'

type CompanyContactsSummary = {
  total: number
  matched: number
  withEmail: number
  verified: number
  campaignReady: number
  eligibleToVerify: number
}

export function isContactVerificationEligible(
  contact: Pick<ProspectContactRead, 'title_match' | 'email' | 'verification_status'>,
): boolean {
  const email = contact.email?.trim() ?? ''
  return contact.title_match === true && email.length > 0 && contact.verification_status === 'unverified'
}

export function summarizeCompanyContacts(contacts: ProspectContactRead[]): CompanyContactsSummary {
  let matched = 0
  let withEmail = 0
  let verified = 0
  let campaignReady = 0
  let eligibleToVerify = 0

  for (const contact of contacts) {
    if (contact.title_match) matched += 1
    if ((contact.email?.trim() ?? '').length > 0) withEmail += 1
    if (contact.pipeline_stage === 'verified') verified += 1
    if (contact.pipeline_stage === 'campaign_ready') campaignReady += 1
    if (isContactVerificationEligible(contact)) eligibleToVerify += 1
  }

  return {
    total: contacts.length,
    matched,
    withEmail,
    verified,
    campaignReady,
    eligibleToVerify,
  }
}
