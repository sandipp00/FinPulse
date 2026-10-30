import { describe, expect, it } from 'vitest'
import { equityRows, sectorCounts } from './equities'

const registry = [
  { id: 'btc', asset_class: 'crypto', live: 'BTC/USDT', name: 'Bitcoin' },
  { id: 'aapl', asset_class: 'stock', live: 'AAPL', name: 'Apple Inc.', sector: 'Technology' },
  { id: 'jpm', asset_class: 'stock', live: 'JPM', name: 'JPMorgan Chase & Co.', sector: 'Financial Services' },
  { id: 'nvda', asset_class: 'stock', live: 'NVDA', name: 'NVIDIA Corporation', sector: 'Technology' },
  { id: 'spx', asset_class: 'index', live: '^GSPC', name: 'S&P 500' },
]

describe('equityRows', () => {
  it('keeps the stocks in registry order, with their names and sectors', () => {
    const rows = equityRows(registry)
    expect(rows.map((r) => r.symbol)).toEqual(['AAPL', 'JPM', 'NVDA'])
    expect(rows[2]).toMatchObject({ name: 'NVIDIA Corporation', sector: 'Technology', type: 'Stock', price: '—' })
  })

  it('uses the stored row of a stock with stored history, but the registry name', () => {
    const [aapl] = equityRows(registry, [{ symbol: 'AAPL', price: '$270.00', daily_change_pct: 1.2, name: 'old' }])
    expect(aapl).toMatchObject({ symbol: 'AAPL', price: '$270.00', daily_change_pct: 1.2, name: 'Apple Inc.' })
  })
})

describe('sectorCounts', () => {
  it('counts each sector in first-seen order', () => {
    expect(sectorCounts(equityRows(registry))).toEqual([
      { sector: 'Technology', count: 2 }, { sector: 'Financial Services', count: 1 },
    ])
  })
})
