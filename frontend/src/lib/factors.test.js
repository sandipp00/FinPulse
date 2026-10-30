import { describe, expect, it } from 'vitest'
import { factorReading, significant } from './factors'

describe('factor readings', () => {
  it('reads market beta at any significance', () => {
    expect(factorReading('Mkt-RF', { value: 1.72, t_stat: 30 })).toMatch(/more than the market: about 1.72%/)
    expect(factorReading('Mkt-RF', { value: 0.18, t_stat: 3 })).toMatch(/less than the market/)
    expect(factorReading('Mkt-RF', { value: 0.98, t_stat: 90 })).toMatch(/one-for-one/)
  })

  it('reads the tilts only when they are distinguishable from zero', () => {
    expect(factorReading('HML', { value: -1.02, t_stat: -9 })).toMatch(/growth/)
    expect(factorReading('HML', { value: 0.71, t_stat: 5 })).toMatch(/value/)
    expect(factorReading('SMB', { value: 0.93, t_stat: 40 })).toMatch(/smaller companies/)
    expect(factorReading('Mom', { value: 0.3, t_stat: 1.1 })).toMatch(/No clear tilt/)
    expect(significant({ value: 1, t_stat: -2.4 })).toBe(true)
    expect(significant({ value: 1, t_stat: null })).toBe(false)
  })
})
