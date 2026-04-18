import type { CompanyListItem } from './types'

type DecisionSource = Pick<CompanyListItem, 'feedback_manual_label' | 'latest_decision' | 'latest_confidence'>

export type DecisionDisplay = {
  badgeLabel: string | null
  badgeValue: string | null
  confidenceLabel: string
  isManual: boolean
}

export function getDecisionDisplay(company: DecisionSource): DecisionDisplay {
  if (company.feedback_manual_label) {
    return {
      badgeLabel: `✏ ${company.feedback_manual_label}`,
      badgeValue: company.feedback_manual_label,
      confidenceLabel: 'Manual',
      isManual: true,
    }
  }

  if (company.latest_decision) {
    return {
      badgeLabel: company.latest_decision,
      badgeValue: company.latest_decision,
      confidenceLabel: company.latest_confidence != null ? `${Math.round(company.latest_confidence * 100)}%` : '—',
      isManual: false,
    }
  }

  return {
    badgeLabel: null,
    badgeValue: null,
    confidenceLabel: '—',
    isManual: false,
  }
}
