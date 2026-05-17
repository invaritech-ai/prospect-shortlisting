export function decisionBgClass(decision: string | null): string {
  if (!decision) return 'oc-badge oc-badge-neutral'
  const value = decision.trim().toLowerCase()
  if (value === 'possible') return 'oc-badge oc-badge-possible'
  if (value === 'unknown')  return 'oc-badge oc-badge-unknown'
  if (value === 'crap')     return 'oc-badge oc-badge-crap'
  return 'oc-badge oc-badge-info'
}
