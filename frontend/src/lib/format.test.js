import { describe, expect, it } from 'vitest'
import { formatPrice } from './format'

describe('formatPrice', () => {
  it('uses the currency of each asset', () => {
    expect(formatPrice(23086.15, '^NSEI')).toBe('₹23,086.15')
    expect(formatPrice(26039.68, '^GDAXI')).toBe('€26,039.68')
  })

  it('shows a plain number for an index measured in points', () => {
    expect(formatPrice(17.2, '^VIX')).toBe('17.20')
  })
})

describe('byCryptoRank', () => {
  it('orders live coins by market cap, unknown ones last in their own order', async () => {
    const { byCryptoRank } = await import('./format')
    expect(byCryptoRank(['SOL/USDT', 'XYZ/USDT', 'BTC/USDT', 'HBAR/USDT', 'ETH/USDT']))
      .toEqual(['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'HBAR/USDT', 'XYZ/USDT'])
  })
})
