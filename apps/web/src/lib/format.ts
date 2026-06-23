const compactCountFormatter = new Intl.NumberFormat(undefined, {
  notation: 'compact',
  maximumFractionDigits: 1,
})

export function formatCompactCount(count: number): string {
  return compactCountFormatter.format(count)
}
