import { describe, expect, it } from 'vitest'
import { curveReading, dvolReading, fundingReading, nearestFuture, putCallReading } from './derivatives'

describe('nearestFuture', () => {
  const futures = [
    { expiry: '2026-10-31', days: 0.6, annualized_pct: null },
    { expiry: '2026-11-27', days: 28, annualized_pct: 5.4 },
    { expiry: '2027-01-29', days: 91, annualized_pct: 5.5 },
    { expiry: '2027-03-26', days: 147, annualized_pct: 5.6 },
  ]

  it('picks the annualized future closest to three months out', () => {
    expect(nearestFuture(futures).expiry).toBe('2027-01-29')
    expect(nearestFuture(futures, 20).expiry).toBe('2026-11-27')
  })

  it('is null when nothing is annualized', () => {
    expect(nearestFuture([futures[0]])).toBeNull()
    expect(nearestFuture(undefined)).toBeNull()
  })
})

describe('readings', () => {
  it('says who pays funding', () => {
    expect(fundingReading(8)).toMatch(/^Positive/)
    expect(fundingReading(-3)).toMatch(/^Negative/)
    expect(fundingReading(0.2)).toMatch(/^About zero/)
    expect(fundingReading(null)).toMatch(/No funding/)
  })

  it('names contango and backwardation', () => {
    expect(curveReading({ expiry: '2027-01-29', annualized_pct: 5.46 })).toBe(
      'Contango: the 2027-01-29 future costs more than spot, a premium of 5.5% a year.')
    expect(curveReading({ expiry: '2026-11-02', annualized_pct: -4.7 })).toMatch(/^Backwardation.*4\.7% a year/)
    expect(curveReading(null)).toMatch(/No dated future/)
  })

  it('reads the put/call ratio and DVOL', () => {
    expect(putCallReading(0.55)).toMatch(/Calls outnumber/)
    expect(putCallReading(1.2)).toMatch(/Puts outnumber/)
    expect(putCallReading(0.85)).toMatch(/balanced/)
    expect(dvolReading({ percentile_1y: 46, low_1y: 33.6, high_1y: 82.6 })).toBe(
      'Higher than on 46% of days in the past year (range 34–83).')
  })
})
