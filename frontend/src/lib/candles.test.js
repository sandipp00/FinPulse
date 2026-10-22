import { describe, expect, it } from 'vitest'
import { applyTick, candleStart } from './candles'

const base = [
  { time: 1_700_000_040, open: 100, high: 105, low: 99, close: 104, volume: 10 },
]

describe('candleStart', () => {
  it('floors to the interval boundary in unix seconds', () => {
    expect(candleStart(1_700_000_059_999, '1m')).toBe(1_700_000_040)
    expect(candleStart(1_700_000_059_999, '1h')).toBe(1_699_999_200)
  })

  it('aligns daily candles to 00:00 UTC', () => {
    expect(candleStart(Date.UTC(2025, 0, 2, 13, 30), '1d')).toBe(Date.UTC(2025, 0, 2) / 1000)
  })
})

describe('applyTick', () => {
  it('returns the same array when there is no tick or no candles', () => {
    expect(applyTick(base, null, '1m')).toBe(base)
    expect(applyTick([], { price: 1, time: 0 }, '1m')).toEqual([])
  })

  it('updates close, high and low of the current candle without mutating', () => {
    const higher = applyTick(base, { price: 110, time: 1_700_000_050_000 }, '1m')
    expect(higher.at(-1)).toMatchObject({ open: 100, high: 110, low: 99, close: 110, volume: 10 })
    expect(base[0].close).toBe(104)

    const lower = applyTick(base, { price: 95, time: 1_700_000_050_000 }, '1m')
    expect(lower.at(-1)).toMatchObject({ high: 105, low: 95, close: 95 })
  })

  it('opens a new candle when the tick is in a later bucket', () => {
    const next = applyTick(base, { price: 106, time: 1_700_000_100_000 }, '1m')
    expect(next).toHaveLength(2)
    expect(next[1]).toEqual({
      time: 1_700_000_100, open: 106, high: 106, low: 106, close: 106, volume: 0,
    })
  })

  it('ignores a tick older than the latest candle', () => {
    expect(applyTick(base, { price: 1, time: 1_699_999_000_000 }, '1m')).toBe(base)
  })
})
