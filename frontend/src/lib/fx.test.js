import { describe, expect, it } from 'vitest'
import { describeRate, formatRate, rateDecimals, toRatePoints } from './fx'

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
