export function formatRelativeTime(iso: string, assumeUtc = false): string {
  const value = assumeUtc && !/[zZ]|[+-]\d{2}:\d{2}$/.test(iso) ? `${iso}Z` : iso
  const mins = Math.floor((Date.now() - new Date(value).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ago`
}
