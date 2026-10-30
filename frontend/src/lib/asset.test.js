import { describe, expect, it } from 'vitest'
import { assetHref, chartInstrument, findAsset, groupAssets } from './asset'

const ASSETS = [
  { id: 'btc', asset_class: 'crypto', live: 'BTC/USDT', stored: 'BTC/USDT' },
  { id: 'gold', asset_class: 'commodity', live: 'XAU/USDT', stored: 'GC=F' },
  { id: 'wti', asset_class: 'commodity', live: 'CL/USDT', eia: 'RWTC' },
  { id: 'aapl', asset_class: 'stock', live: 'AAPL', stored: 'AAPL' },
  { id: 'eurusd', asset_class: 'fx', live: 'EUR/USD', ecb: 'EUR/USD' },
]

describe('asset helpers', () => {
  it('finds an asset by id or by any of its symbols', () => {
    expect(findAsset(ASSETS, 'gold').id).toBe('gold')
    expect(findAsset(ASSETS, 'GC=F').id).toBe('gold')
    expect(findAsset(ASSETS, 'XAU/USDT').id).toBe('gold')
    expect(findAsset(ASSETS, 'RWTC').id).toBe('wti')
    expect(findAsset(ASSETS, 'DOGE')).toBeNull()
    expect(findAsset(ASSETS, '')).toBeNull()
  })

  it('charts live exchange history first, then stored history, else nothing', () => {
    const instruments = [{ symbol: 'XAU/USDT' }, { symbol: 'GC=F' }, { symbol: 'AAPL' }]
    expect(chartInstrument(ASSETS[1], instruments).symbol).toBe('XAU/USDT')
    expect(chartInstrument(ASSETS[3], instruments).symbol).toBe('AAPL')
    expect(chartInstrument(ASSETS[4], instruments)).toBeNull()
  })

  it('links by id or symbol and groups by class in a fixed order', () => {
    expect(assetHref('GC=F')).toBe('/asset?asset=GC%3DF')
    expect(groupAssets(ASSETS).map((g) => g.assetClass)).toEqual(['crypto', 'stock', 'commodity', 'fx'])
  })
})
