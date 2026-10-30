// Plain words for CFTC positioning (backend/cftc.py).

/**
 * What a 3-year percentile of net positioning means. It is relative to the market's own
 * history, so "bullish" can still be net short (Bitcoin's funds are usually short).
 */
export function percentileReading(pct) {
  if (pct == null) return 'Not enough history to compare.'
  if (pct >= 90) return `Speculators are near their most bullish in three years (${pct}th percentile).`
  if (pct <= 10) return `Speculators are near their most bearish in three years (${pct}th percentile).`
  if (pct >= 60) return `Speculators are more bullish than usual for the last three years (${pct}th percentile).`
  if (pct <= 40) return `Speculators are more bearish than usual for the last three years (${pct}th percentile).`
  return `Speculators are around their middle of the last three years (${pct}th percentile).`
}
