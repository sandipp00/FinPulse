import { describe, expect, it } from 'vitest'
import { BOARD, boardLabel, coverage, marketsOpen, movers } from './overview'

const tick = (symbol, assetClass, change, window = '1d') => ({ symbol, asset_class: assetClass, change_pct_24h: change, change_window: window })

describe('movers', () => {
  const ticks = Object.fromEntries([
    tick('INTC', 'stock', -30.9), tick('LLY', 'stock', 3.5), tick('BTC/USDT', 'crypto', -5.5, '24h'),
    tick('CL/USDT', 'commodity', 1.9, '24h'), tick('^N225', 'index', -2.1), tick('EUR/USD', 'fx', 0.2),
    tick('XRP/USDT', 'crypto', null, '24h'),
  ].map((t) => [t.symbol, t]))

  it('ranks stocks, crypto and commodities, biggest first, leaving out indices, FX and missing changes', () => {
    const { gainers, losers } = movers(ticks)
    expect(gainers.map((m) => m.symbol)).toEqual(['LLY', 'CL/USDT'])
    expect(losers.map((m) => m.symbol)).toEqual(['INTC', 'BTC/USDT'])
    expect(losers[1]).toMatchObject({ assetClass: 'crypto', change: -5.5, window: '24h' })
  })

  it('caps each list', () => {
    expect(movers(ticks, 1).losers.map((m) => m.symbol)).toEqual(['INTC'])
  })
})

describe('marketsOpen', () => {
  const exchanges = [
    { id: 'nyse', session: { start: 100, end: 500 } },
    { id: 'lse', session: { start: 900, end: 1500 } },
    { id: 'tse', session: { start: 700, end: 1000 } },
    { id: 'old', session: { start: 0, end: 50 } },
  ]

  it('lists the open exchanges and the next to open', () => {
    const result = marketsOpen(exchanges, 200)
    expect(result.open.map((e) => e.id)).toEqual(['nyse'])
    expect(result.next).toEqual({ exchange: exchanges[2], seconds: 500 })
    expect(result.total).toBe(4)
  })

  it('copes with no data', () => {
    expect(marketsOpen(undefined, 0)).toEqual({ open: [], next: null, total: 0 })
  })
})

describe('coverage and the board', () => {
  it('counts the registry by class', () => {
    expect(coverage([{ asset_class: 'stock' }, { asset_class: 'stock' }, { asset_class: 'fx' }])).toEqual({ stock: 2, fx: 1 })
  })

  it('labels the board briefly', () => {
    expect(boardLabel('^IXIC', 'Nasdaq Composite')).toBe('Nasdaq')
    expect(boardLabel('EUR/USD', 'Euro / US dollar')).toBe('EUR/USD')
    expect(boardLabel('BTC/USDT', 'Bitcoin')).toBe('Bitcoin')
  })

  it('has four benchmarks per panel and no repeats', () => {
    const all = BOARD.flatMap((panel) => panel.symbols)
    expect(BOARD.every((panel) => panel.symbols.length === 4)).toBe(true)
    expect(new Set(all).size).toBe(all.length)
  })
})
