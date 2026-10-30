import { describe, expect, it } from 'vitest'
import { byDate, daysUntil, formatDay, formatEps, growthVsLastYear, reportsWithin } from './earnings'

const upcoming = [
  { symbol: 'AAPL', date: '2026-11-02' }, { symbol: 'PLTR', date: '2026-11-02' },
  { symbol: 'NVDA', date: '2026-11-17' }, { symbol: 'MU', date: '2026-12-16' },
]

describe('earnings helpers', () => {
  it('formats days and EPS', () => {
    expect(formatDay('2026-11-02')).toBe('Mon 2 Nov')
    expect(formatEps(2.49)).toBe('$2.49')
    expect(formatEps(-0.3)).toBe('-$0.30')
    expect(formatEps(null)).toBe('—')
  })

  it('counts days and picks the reports within a window', () => {
    expect(daysUntil('2026-11-02', '2026-10-31')).toBe(2)
    expect(reportsWithin(upcoming, '2026-10-31', 7).map((r) => r.symbol)).toEqual(['AAPL', 'PLTR'])
  })

  it('groups by date in order', () => {
    expect(byDate(upcoming).map(([day, rows]) => [day, rows.length])).toEqual([
      ['2026-11-02', 2], ['2026-11-17', 1], ['2026-12-16', 1],
    ])
  })

  it('compares the forecast with a year earlier only when both are positive figures', () => {
    expect(growthVsLastYear({ eps_forecast: 2.49, eps_last_year: 1.24 })).toBe('+101% on a year ago')
    expect(growthVsLastYear({ eps_forecast: 1.57, eps_last_year: 1.95 })).toBe('-19% on a year ago')
    expect(growthVsLastYear({ eps_forecast: 0.5, eps_last_year: -0.2 })).toBeNull()
    expect(growthVsLastYear({ eps_forecast: null, eps_last_year: 1 })).toBeNull()
  })
})
