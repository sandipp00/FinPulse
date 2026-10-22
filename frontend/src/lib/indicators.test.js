import { describe, expect, it } from 'vitest'
import { bollinger, ema, macd, rsi, sma } from './indicators'

describe('sma', () => {
  it('averages a rolling window and pads the warm-up with null', () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4])
  })
})

describe('ema', () => {
  it('seeds with the SMA and then smooths', () => {
    const result = ema([1, 2, 3, 4, 5], 3)
    // k = 0.5, seed = SMA(1,2,3) = 2, then 4*.5+2*.5 = 3 and 5*.5+3*.5 = 4.
    expect(result[0]).toBeNull()
    expect(result[1]).toBeNull()
    expect(result[2]).toBe(2)
    expect(result[3]).toBe(3)
    expect(result[4]).toBe(4)
  })

  it('returns all nulls when there is not enough data', () => {
    expect(ema([1, 2], 5)).toEqual([null, null])
  })
})

describe('bollinger', () => {
  it('is flat on constant prices and brackets the mean otherwise', () => {
    const flat = bollinger([5, 5, 5, 5], 3)
    expect(flat.upper[3]).toBe(5)
    expect(flat.lower[3]).toBe(5)

    // Window [1,2,3]: mean 2, population std sqrt(2/3).
    const { upper, middle, lower } = bollinger([1, 2, 3], 3, 2)
    const deviation = Math.sqrt(2 / 3)
    expect(middle[2]).toBe(2)
    expect(upper[2]).toBeCloseTo(2 + 2 * deviation, 10)
    expect(lower[2]).toBeCloseTo(2 - 2 * deviation, 10)
  })
})

describe('rsi', () => {
  it('is 100 when price only rises and 0 when it only falls', () => {
    const rising = Array.from({ length: 20 }, (_, i) => i + 1)
    const falling = [...rising].reverse()
    expect(rsi(rising, 14).at(-1)).toBe(100)
    expect(rsi(falling, 14).at(-1)).toBe(0)
  })

  it('matches the Wilder reference value for the classic example', () => {
    // Wilder's textbook closing prices; first RSI(14) is ~70.46.
    const closes = [
      44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
      46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
    ]
    expect(rsi(closes, 14)[14]).toBeCloseTo(70.46, 1)
  })

  it('stays within 0-100 on noisy data', () => {
    const noisy = Array.from({ length: 60 }, (_, i) => 100 + Math.sin(i) * 5 + i * 0.1)
    rsi(noisy).filter((v) => v != null).forEach((v) => {
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(100)
    })
  })
})

describe('macd', () => {
  it('lines up with the input and defines each series at the right index', () => {
    const closes = Array.from({ length: 60 }, (_, i) => 100 + i)
    const { line, signal, histogram } = macd(closes)

    expect(line).toHaveLength(60)
    expect(line[24]).toBeNull()
    expect(line[25]).not.toBeNull() // slow EMA (26) first defined
    expect(signal[32]).toBeNull()
    expect(signal[33]).not.toBeNull() // 9 values after the MACD line starts
    expect(histogram[33]).toBeCloseTo(line[33] - signal[33], 10)
  })

  it('is positive in a steady uptrend', () => {
    const closes = Array.from({ length: 60 }, (_, i) => 100 + i)
    expect(macd(closes).line.at(-1)).toBeGreaterThan(0)
  })
})
