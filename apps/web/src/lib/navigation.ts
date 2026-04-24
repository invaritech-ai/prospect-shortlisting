export type ActiveView =
  | 'dashboard'
  | 'operations'
  | 'campaigns'
  | 'settings'
  | 'full-pipeline'
  | 's1-scraping'
  | 's2-ai'
  | 's3-contacts'
  | 's4-reveal'
  | 's5-validation'
  | 'queue-history'

export interface AppRouteState {
  view: ActiveView
  campaignId: string | null
}

export const DEFAULT_ACTIVE_VIEW: ActiveView = 'dashboard'

const ACTIVE_VIEW_VALUES: ActiveView[] = [
  'dashboard',
  'operations',
  'campaigns',
  'settings',
  'full-pipeline',
  's1-scraping',
  's2-ai',
  's3-contacts',
  's4-reveal',
  's5-validation',
  'queue-history',
]

export function isActiveView(value: string | null): value is ActiveView {
  return value !== null && ACTIVE_VIEW_VALUES.includes(value as ActiveView)
}

export function parseRouteState(search: string): AppRouteState {
  const params = new URLSearchParams(search)
  const viewParam = params.get('view')
  const campaignParam = params.get('campaign')

  return {
    view: isActiveView(viewParam) ? viewParam : DEFAULT_ACTIVE_VIEW,
    campaignId: campaignParam && campaignParam.trim() ? campaignParam : null,
  }
}

export function buildRouteSearch(state: AppRouteState): string {
  const params = new URLSearchParams()
  params.set('view', state.view)
  if (state.campaignId) params.set('campaign', state.campaignId)
  const query = params.toString()
  return query ? `?${query}` : ''
}
