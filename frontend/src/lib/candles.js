export const INTERVALS = ['1m', '15m', '1h', '1d']

export const INTERVAL_MS = {
  '1m': 60_000,
  '15m': 900_000,
  '1h': 3_600_000,
  '1d': 86_400_000,
}

/** Unix-seconds start time of the candle that contains `timeMs`. */
export function candleStart(timeMs, interval) {
  const size = INTERVAL_MS[interval]
  return Math.floor(timeMs / size) * size / 1000
}

/**
 * Fold a live tick into a candle series without mutating it: update the
 * latest candle's close/high/low, or open a new candle when the tick falls in
 * a later bucket. Ticks older than the latest candle are ignored.
 */
export function applyTick(candles, tick, interval) {
  if (!tick || candles.length === 0) return candles

  const start = candleStart(tick.time, interval)
  const last = candles.at(-1)

  if (start < last.time) return candles

  if (start === last.time) {
    return [
      ...candles.slice(0, -1),
      {
        ...last,
        close: tick.price,
        high: Math.max(last.high, tick.price),
        low: Math.min(last.low, tick.price),
      },
    ]
  }

  return [
    ...candles,
    {
      time: start,
      open: tick.price,
      high: tick.price,
      low: tick.price,
      close: tick.price,
      volume: 0,
    },
  ]
}
