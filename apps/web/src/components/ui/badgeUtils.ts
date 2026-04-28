export function decisionBgClass(decision: string | null): string {
  if (!decision) return 'bg-slate-100 text-slate-600'
  const value = decision.trim().toLowerCase()
  if (value === 'possible') return 'bg-emerald-50 text-emerald-800'
  if (value === 'unknown') return 'bg-amber-50 text-amber-800'
  if (value === 'crap') return 'bg-rose-50 text-rose-800'
  return 'bg-indigo-50 text-indigo-800'
}
