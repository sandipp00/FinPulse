import { describe, expect, it } from 'vitest'
import { changeOf, summarize } from './marketSummary'

const ASSETS = [
  { symbol: 'BTC/USDT', name: 'Bitcoin', daily_change_pct: 1 },
  { symbol: 'HYPE/USDT', name: 'Hyperliquid' },
  { symbol: 'BNB/USDT', name: 'BNB' },
  { symbol: 'AAPL', name: 'Apple Inc.', daily_change_pct: 1.5 },
  { symbol: 'NEW/USDT', name: 'New' },
]
const TICKS = {
  'BTC/USDT': { change_pct_24h: -3 },
  'HYPE/USDT': { change_pct_24h: 15.5 },
  'BNB/USDT': { change_pct_24h: -6.5 },
}

describe('market summary', () => {
  it('prefers the live change and falls back to the stored daily change', () => {
    expect(changeOf(ASSETS[0], TICKS)).toBe(-3)
    expect(changeOf(ASSETS[3], TICKS)).toBe(1.5)
    expect(changeOf(ASSETS[4], TICKS)).toBeNull()
  })

  it('counts ups and downs, averages the moves, and names the best and worst', () => {
    const summary = summarize(ASSETS, TICKS)
    expect(summary).toMatchObject({ count: 5, priced: 4, up: 2, down: 2 })
    expect(summary.average).toBeCloseTo((-3 + 15.5 - 6.5 + 1.5) / 4)
    expect(summary.best).toEqual({ symbol: 'HYPE/USDT', name: 'Hyperliquid', change: 15.5 })
    expect(summary.worst.symbol).toBe('BNB/USDT')
  })

  it('handles nothing priced yet', () => {
    expect(summarize([ASSETS[4]], {})).toMatchObject({ priced: 0, average: null, best: null, worst: null })
  })
})
