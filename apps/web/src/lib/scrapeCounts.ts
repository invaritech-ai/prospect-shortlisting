type ScrapeFailureCounts = {
  scrape_failed?: number
  scrape_soft_fail?: number
  scrape_permanent_fail?: number
}

export function getDisplayedScrapeFailedCount(counts: ScrapeFailureCounts | null | undefined): number {
  if (!counts) return 0
  if (typeof counts.scrape_failed === 'number') return Math.max(0, counts.scrape_failed)
  return Math.max(0, counts.scrape_soft_fail ?? 0) + Math.max(0, counts.scrape_permanent_fail ?? 0)
}
