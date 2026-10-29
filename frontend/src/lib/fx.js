// Formatting helpers for FX rates (see backend/fx_api.py).

/** Decimals that suit a rate's size: 1.1130, 95.27, 165.40. */
export function rateDecimals(rate) {
  return Math.abs(rate) < 10 ? 4 : 2
}

export function formatRate(rate) {
  if (rate == null || !Number.isFinite(Number(rate))) return '—'
  const number = Number(rate)
  return number.toLocaleString('en-US', { minimumFractionDigits: rateDecimals(number), maximumFractionDigits: rateDecimals(number) })
}

/** What one unit of the base buys: "1 USD = 95.27 INR". */
export function describeRate(base, quote, rate) {
  return rate == null ? '—' : `1 ${base} = ${formatRate(rate)} ${quote}`
}

/** FX history as chart points ({time, value}); dates with no publication are simply absent. */
export function toRatePoints(observations) {
  return observations.map((row) => ({ time: row.date, value: row.rate }))
}
