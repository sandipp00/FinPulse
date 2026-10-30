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

/** Candles with the newest bar following the live tick, so a chart moves between fetches. */
export function withLiveTick(candles, tick) {
  const last = candles.at(-1)
  if (!last || !tick?.price || !tick.time || tick.time / 1000 < last.time) return candles
  const price = tick.price
  return [...candles.slice(0, -1), { ...last, close: price, high: Math.max(last.high, price), low: Math.min(last.low, price) }]
}
