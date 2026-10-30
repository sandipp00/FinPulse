// Plain-language readings of the Deribit derivatives figures (backend/deribit.py).

/** The dated future nearest `targetDays` out that has an annualized premium, or null. */
export function nearestFuture(futures, targetDays = 90) {
  const annualized = (futures ?? []).filter((f) => f.annualized_pct != null)
  if (annualized.length === 0) return null
  return annualized.reduce((best, f) => (Math.abs(f.days - targetDays) < Math.abs(best.days - targetDays) ? f : best))
}

/** Who pays whom at this funding rate. */
export function fundingReading(annualizedPct) {
  if (annualizedPct == null) return 'No funding rate reported.'
  if (Math.abs(annualizedPct) < 0.5) return 'About zero: neither side pays much to hold its position.'
  return annualizedPct > 0
    ? 'Positive: holders of long positions pay holders of short ones, so more traders are betting on a rise.'
    : 'Negative: holders of short positions pay holders of long ones, so more traders are betting on a fall.'
}

/** Contango (futures above spot) or backwardation (below). */
export function curveReading(future) {
  if (!future) return 'No dated future far enough out to compare.'
  const pct = future.annualized_pct
  if (Math.abs(pct) < 0.5) return 'Flat: futures trade at about the spot price.'
  return pct > 0
    ? `Contango: the ${future.expiry} future costs more than spot, a premium of ${pct.toFixed(1)}% a year.`
    : `Backwardation: the ${future.expiry} future costs less than spot, a discount of ${Math.abs(pct).toFixed(1)}% a year.`
}

/** What the put/call open-interest ratio leans towards. */
export function putCallReading(ratio) {
  if (ratio == null) return 'No options open.'
  if (ratio < 0.7) return 'Calls outnumber puts: positioning leans towards a rise.'
  if (ratio > 1) return 'Puts outnumber calls: more protection against a fall is held.'
  return 'Calls and puts are fairly balanced.'
}

/** Where today's DVOL sits in its past year. */
export function dvolReading(dvol) {
  if (!dvol) return ''
  return `Higher than on ${dvol.percentile_1y}% of days in the past year (range ${dvol.low_1y.toFixed(0)}–${dvol.high_1y.toFixed(0)}).`
}
