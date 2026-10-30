import { describe, expect, it } from 'vitest'
import {
  alignForComparison,
  barReturns,
  buildExplorerQuery,
  formatBarTime,
  formatQuote,
  limitOptions,
  parseExplorerQuery,
  resolveExplorerState,
  searchInstruments,
  summarizeReturns,
  volumeUnit,
} from './explorer'

const DAY = 86_400
const bar = (time, close, extra = {}) => ({ time, open: close, high: close, low: close, close, volume: 10, ...extra })

const INSTRUMENTS = [
  { symbol: 'BTC/USDT', asset_class: 'crypto', live: true, intervals: ['1m', '15m', '1h', '1d'] },
  { symbol: 'ETH/USDT', asset_class: 'crypto', live: true, intervals: ['1m', '15m', '1h', '1d'] },
  { symbol: 'AAPL', asset_class: 'stock', live: false, intervals: ['1d'] },
  { symbol: '^NSEI', asset_class: 'index', live: false, intervals: ['1d'] },
]

describe('searchInstruments', () => {
  it('returns everything for an empty query', () => {
    expect(searchInstruments(INSTRUMENTS, '  ')).toHaveLength(4)
  })

  it('matches symbols without their decoration, and names', () => {
    expect(searchInstruments(INSTRUMENTS, 'btc').map((i) => i.symbol)).toEqual(['BTC/USDT'])
    expect(searchInstruments(INSTRUMENTS, 'nsei').map((i) => i.symbol)).toEqual(['^NSEI'])
    expect(searchInstruments(INSTRUMENTS, 'nifty').map((i) => i.symbol)).toEqual(['^NSEI'])
    expect(searchInstruments(INSTRUMENTS, 'apple').map((i) => i.symbol)).toEqual(['AAPL'])
  })

  it('ranks an exact or prefix match above a match elsewhere', () => {
    // "eth" is ETH's symbol and appears inside nothing else; "usdt" is in both pairs.
    expect(searchInstruments(INSTRUMENTS, 'eth')[0].symbol).toBe('ETH/USDT')
    expect(searchInstruments(INSTRUMENTS, 'usdt').map((i) => i.symbol)).toEqual(['BTC/USDT', 'ETH/USDT'])
  })

  it('finds nothing for an unknown query', () => {
    expect(searchInstruments(INSTRUMENTS, 'tsla')).toEqual([])
  })
})

describe('options and units', () => {
  it('offers bar counts each source accepts', () => {
    expect(limitOptions('binance')).toEqual([100, 250, 500, 1000])
    expect(Math.max(...limitOptions('binance'))).toBeLessThanOrEqual(1000)
    expect(limitOptions('database').at(-1)).toBe(5000)
  })

  it('names the volume unit, or none for an index', () => {
    expect(volumeUnit(INSTRUMENTS[0])).toBe('BTC')
    expect(volumeUnit(INSTRUMENTS[2])).toBe('shares')
    expect(volumeUnit(INSTRUMENTS[3])).toBeNull()
    expect(volumeUnit({ symbol: 'GC=F', asset_class: 'commodity' })).toBe('contracts')
    expect(volumeUnit({ symbol: 'XAU/USDT', asset_class: 'commodity' })).toBe('XAU')
    expect(volumeUnit({ symbol: 'EUR/USD', asset_class: 'fx' })).toBeNull()
  })
})

describe('returns', () => {
  const candles = [bar(0, 100, { high: 105, low: 95 }), bar(DAY, 110), bar(2 * DAY, 99, { volume: 40 })]

  it('computes bar returns from consecutive closes', () => {
    const returns = barReturns(candles).map((point) => point.value)
    expect(returns[0]).toBeCloseTo(10)
    expect(returns[1]).toBeCloseTo(-10)
  })

  it('summarizes the window', () => {
    const summary = summarizeReturns(candles)
    expect(summary.bars).toBe(3)
    expect(summary.periodReturnPct).toBeCloseTo(-1)
    expect(summary.logReturnPct).toBeCloseTo(Math.log(0.99) * 100)
    expect(summary.bestBarPct).toBeCloseTo(10)
    expect(summary.worstBarPct).toBeCloseTo(-10)
    expect(summary.barVolatilityPct).toBeCloseTo(Math.sqrt(200))
    expect(summary.high).toBe(110)
    expect(summary.low).toBe(95)
    expect(summary.averageVolume).toBeCloseTo(20)
  })

  it('says when the source reports no volume instead of averaging zeros', () => {
    const summary = summarizeReturns(candles.map((candle) => ({ ...candle, volume: 0 })))
    expect(summary.volumeReported).toBe(false)
    expect(summary.averageVolume).toBeNull()
  })

  it('needs at least two bars', () => {
    expect(summarizeReturns([])).toBeNull()
    expect(summarizeReturns([bar(0, 1)])).toBeNull()
    expect(summarizeReturns(undefined)).toBeNull()
  })
})

describe('alignForComparison', () => {
  it('keeps only shared days and rebases both to 100 at the first one', () => {
    // A trades on days 0-3; B is missing day 1 and is stamped a few hours into each day.
    const a = [bar(0, 100), bar(DAY, 120), bar(2 * DAY, 110), bar(3 * DAY, 150)]
    const b = [bar(4 * 3600, 50), bar(2 * DAY + 4 * 3600, 55), bar(3 * DAY + 4 * 3600, 40)]

    const result = alignForComparison(a, b, '1d')

    expect(result.shared).toBe(3)
    expect(result.points.map((p) => p.time)).toEqual([0, 2 * DAY, 3 * DAY])
    expect(result.points[0]).toEqual({ time: 0, primary: 100, other: 100 })
    expect(result.points[1].primary).toBeCloseTo(110)
    expect(result.points[1].other).toBeCloseTo(110)
    expect(result.primaryReturnPct).toBeCloseTo(50)
    expect(result.otherReturnPct).toBeCloseTo(-20)
  })

  it('matches intraday bars on exact time only', () => {
    const a = [bar(0, 100), bar(3600, 101)]
    const b = [bar(60, 100), bar(3660, 101)]
    expect(alignForComparison(a, b, '1h').shared).toBe(0)
    expect(alignForComparison(a, a, '1h').shared).toBe(2)
  })

  it('returns no points when fewer than two bars overlap', () => {
    const result = alignForComparison([bar(0, 1), bar(DAY, 2)], [bar(5 * DAY, 1)], '1d')
    expect(result.points).toEqual([])
    expect(result.primaryReturnPct).toBeNull()
  })
})

describe('URL state', () => {
  it('round-trips through the query string', () => {
    const state = { symbol: '^NSEI', interval: '1d', limit: 250, compare: 'AAPL' }
    expect(parseExplorerQuery(buildExplorerQuery(state))).toEqual(state)
  })

  it('ignores junk', () => {
    expect(parseExplorerQuery('?limit=abc')).toEqual({ symbol: '', interval: '', limit: null, compare: '' })
    expect(buildExplorerQuery({})).toBe('')
  })
})

describe('resolveExplorerState', () => {
  it('falls back to the first instrument and sensible defaults', () => {
    const state = resolveExplorerState({ symbol: 'NOPE', interval: '', limit: null, compare: '' }, INSTRUMENTS)
    expect(state.symbol).toBe('BTC/USDT')
    expect(state.interval).toBe('1d')
    expect(state.limit).toBe(500)
  })

  it('moves a stored instrument to daily bars and its own bar counts', () => {
    const state = resolveExplorerState({ symbol: 'AAPL', interval: '1h', limit: 1000, compare: '' }, INSTRUMENTS)
    expect(state.interval).toBe('1d')
    expect(state.limit).toBe(500)
  })

  it('drops a comparison that cannot share the interval or is the same instrument', () => {
    const intraday = resolveExplorerState({ symbol: 'BTC/USDT', interval: '1h', limit: 500, compare: 'AAPL' }, INSTRUMENTS)
    expect(intraday.compare).toBe('')
    const same = resolveExplorerState({ symbol: 'AAPL', interval: '1d', limit: 500, compare: 'AAPL' }, INSTRUMENTS)
    expect(same.compare).toBe('')
    const ok = resolveExplorerState({ symbol: 'BTC/USDT', interval: '1h', limit: 500, compare: 'ETH/USDT' }, INSTRUMENTS)
    expect(ok.compare).toBe('ETH/USDT')
  })

  it('is null when nothing is supported yet', () => {
    expect(resolveExplorerState({ symbol: 'AAPL' }, [])).toBeNull()
  })
})

describe('formatQuote', () => {
  it('uses the symbol of an ISO currency', () => {
    expect(formatQuote(345.785, 'USD')).toBe('$345.79')
    expect(formatQuote(22622.7, 'INR')).toBe('₹22,622.70')
  })

  it('writes out a currency without a symbol, such as a stablecoin', () => {
    expect(formatQuote(80911.96, 'USDT')).toBe('80,911.96 USDT')
    expect(formatQuote(1.29345, 'USDT')).toBe('1.2935 USDT')
  })

  it('shows a bare number when the currency is unknown, and a dash for no value', () => {
    expect(formatQuote(12.5, null)).toBe('12.50')
    expect(formatQuote(null, 'USD')).toBe('—')
  })
})

describe('formatBarTime', () => {
  it('shows the UTC date for daily bars and the UTC time for intraday bars', () => {
    expect(formatBarTime(1791763200, '1d')).toBe('12 Oct 2026')
    expect(formatBarTime(1791763200 + 3600 * 13.5, '1h')).toBe('12 Oct, 13:30 UTC')
    expect(formatBarTime(null, '1d')).toBe('—')
  })
})
