import { describe, expect, it } from 'vitest'
import { describeRate, formatRate, rateDecimals, toRatePoints, withLiveTick } from './fx'

describe('FX formatting', () => {
  it('uses four decimals below 10 and two above', () => {
    expect(rateDecimals(1.113)).toBe(4)
    expect(rateDecimals(95.27)).toBe(2)
    expect(formatRate(1.113)).toBe('1.1130')
    expect(formatRate(0.8512)).toBe('0.8512')
    expect(formatRate(95.2741)).toBe('95.27')
    expect(formatRate(1650.5)).toBe('1,650.50')
    expect(formatRate(null)).toBe('—')
  })

  it('reads as what one unit of the base buys', () => {
    expect(describeRate('USD', 'INR', 95.2741)).toBe('1 USD = 95.27 INR')
    expect(describeRate('USD', 'INR', null)).toBe('—')
  })

  it('maps history to chart points without inventing missing days', () => {
    expect(toRatePoints([{ date: '2026-10-23', rate: 1.1 }, { date: '2026-10-26', rate: 1.2 }]))
      .toEqual([{ time: '2026-10-23', value: 1.1 }, { time: '2026-10-26', value: 1.2 }])
  })
})

describe('withLiveTick', () => {
  const candles = [
    { time: 100, open: 1.1, high: 1.12, low: 1.09, close: 1.11, volume: 0 },
    { time: 160, open: 1.11, high: 1.115, low: 1.108, close: 1.112, volume: 0 },
  ]

  it('moves the newest bar to the live price, stretching its range', () => {
    const out = withLiveTick(candles, { price: 1.118, time: 170_000 })
    expect(out.at(-1)).toEqual({ time: 160, open: 1.11, high: 1.118, low: 1.108, close: 1.118, volume: 0 })
    expect(out[0]).toBe(candles[0])
  })

  it('leaves the candles alone for an older tick or no tick', () => {
    expect(withLiveTick(candles, { price: 1.2, time: 150_000 })).toBe(candles)
    expect(withLiveTick(candles, undefined)).toBe(candles)
    expect(withLiveTick([], { price: 1.2, time: 170_000 })).toEqual([])
  })
})
