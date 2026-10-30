import { describe, expect, it } from 'vitest'
import { filterIndices, netChange, regionSummary } from './worldIndices'

const INDICES = [
  { symbol: '^GSPC', name: 'S&P 500', region: 'Americas', country: 'United States' },
  { symbol: '^FTSE', name: 'FTSE 100', region: 'Europe', country: 'United Kingdom' },
  { symbol: '^N225', name: 'Nikkei 225', region: 'Asia-Pacific', country: 'Japan' },
]

describe('world indices helpers', () => {
  it('filters by region and by name, country or symbol', () => {
    expect(filterIndices(INDICES, { region: 'Europe' }).map((i) => i.symbol)).toEqual(['^FTSE'])
    expect(filterIndices(INDICES, { query: 'japan' }).map((i) => i.symbol)).toEqual(['^N225'])
    expect(filterIndices(INDICES, { query: '^gspc' }).map((i) => i.symbol)).toEqual(['^GSPC'])
    expect(filterIndices(INDICES, { region: 'Europe', query: 'nikkei' })).toEqual([])
    expect(filterIndices(INDICES)).toHaveLength(3)
  })

  it('summarises a region: live and open counts, average change, ups and downs', () => {
    const ticks = {
      '^GSPC': { change_pct_24h: 1.0, market_open: false },
      '^FTSE': { change_pct_24h: -0.5, market_open: true },
      '^N225': { change_pct_24h: 0.5, market_open: true },
    }
    const statuses = { '^GSPC': 'closed', '^FTSE': 'delayed', '^N225': 'live' }
    expect(regionSummary(INDICES, ticks, statuses)).toEqual({ count: 3, live: 1, open: 2, averageChange: 1 / 3, up: 2, down: 1 })
    expect(regionSummary(INDICES, {}, {}).averageChange).toBeNull()
  })

  it('works out the net change in points', () => {
    expect(netChange({ price: 7720.39, previous_close: 7743.98 })).toBeCloseTo(-23.59)
    expect(netChange({ price: 1 })).toBeNull()
  })
})
