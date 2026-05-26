export function formatCompactCount(count: number): string {
  if (count >= 1_000_000) {
    const value = count / 1_000_000
    return `${value >= 10 ? Math.round(value) : Number(value.toFixed(1))}M`
  }
  if (count >= 1_000) {
    const value = count / 1_000
    return `${value >= 10 ? Math.round(value) : Number(value.toFixed(1))}K`
  }
  return String(count)
}
