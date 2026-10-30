import { describe, expect, it } from 'vitest'
import { marketOf, symbolsInMarket } from './liveMarkets'

describe('live markets', () => {
  const ticks = {
    'BTC/USDT': { symbol: 'BTC/USDT', market: 'crypto' },
    'ETH/USDT': { symbol: 'ETH/USDT' },
    'XAU/USDT': { symbol: 'XAU/USDT', market: 'tradfi' },
    AAPL: { symbol: 'AAPL', market: 'quotes' },
  }

  it('treats ticks without a market as crypto', () => {
    expect(marketOf(ticks['ETH/USDT'])).toBe('crypto')
    expect(marketOf(undefined)).toBe('crypto')
  })

  it('splits symbols by market', () => {
    expect(symbolsInMarket(ticks, 'crypto')).toEqual(['BTC/USDT', 'ETH/USDT'])
    expect(symbolsInMarket(ticks, 'tradfi')).toEqual(['XAU/USDT'])
    expect(symbolsInMarket(ticks, 'quotes')).toEqual(['AAPL'])
  })
})
