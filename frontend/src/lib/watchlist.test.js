import { describe, expect, it } from 'vitest'
import { MAX_ITEMS, add, move, remove, resolve } from './watchlist'

describe('editing the list', () => {
  it('moves items up and down, and not past either end', () => {
    expect(move(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c'])
    expect(move(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'c', 'b'])
    expect(move(['a', 'b'], 0, -1)).toEqual(['a', 'b'])
    expect(move(['a', 'b'], 1, 1)).toEqual(['a', 'b'])
  })

  it('adds once, at the end, up to the limit; removes', () => {
    expect(add(['a'], 'b')).toEqual(['a', 'b'])
    expect(add(['a'], 'a')).toEqual(['a'])
    expect(add(['a'], '')).toEqual(['a'])
    const full = Array.from({ length: MAX_ITEMS }, (_, i) => `s${i}`)
    expect(add(full, 'x')).toBe(full)
    expect(remove(['a', 'b'], 'a')).toEqual(['b'])
  })
})

describe('resolve', () => {
  const defaults = [{ symbol: 'AAPL', name: 'Apple Inc.', price: '$343.00', stored: true, type: 'Stock' }]
  const instruments = [{ symbol: 'NVDA', asset_class: 'stock' }, { symbol: '^N225', asset_class: 'index' }, { symbol: 'AAPL', asset_class: 'stock' }]

  it('keeps the order, prefers the default row, builds the rest and drops unknown symbols', () => {
    const rows = resolve(['^N225', 'AAPL', 'GONE', 'NVDA'], defaults, instruments)
    expect(rows.map((r) => r.symbol)).toEqual(['^N225', 'AAPL', 'NVDA'])
    expect(rows[1]).toBe(defaults[0])
    expect(rows[0]).toMatchObject({ type: 'Index', name: 'Nikkei 225', price: '—', stored: false })
    expect(rows[2]).toMatchObject({ type: 'Stock', name: 'NVIDIA Corporation' })
  })
})
