import { describe, expect, it } from 'vitest'
import { buildBrief } from './research'

const tick = { price: 100, change_pct_24h: -2.5, high_24h: 110, low_24h: 90 }

const signal = (rating, score, overrides = {}) => ({
  rating,
  score,
  votes: { bullish: 3, bearish: 1, neutral: 2 },
  reasons: [
    { rule: 'trend', vote: 1, weight: 1.0, text: 'Price is above the 50-candle average' },
    { rule: 'bollinger', vote: -1, weight: 0.75, text: 'Price closed above the upper band' },
    { rule: 'volume', vote: 0, weight: 0.5, text: 'Volume is normal' },
    { rule: 'macd', vote: 1, weight: 1.0, text: 'MACD histogram is positive' },
  ],
  ...overrides,
})

const risk = (symbol, vol, extra = {}) => ({
  symbol,
  observations: 500,
  start_date: '2024-06-01',
  annualized_volatility_pct: vol,
  recent_volatility_pct: vol,
  max_drawdown_pct: -50,
  max_drawdown_date: '2025-03-01',
  current_drawdown_pct: -20,
  var_95_pct: -4,
  expected_shortfall_pct: -6,
  worst_day_pct: -12,
  worst_day_date: '2025-02-10',
  ...extra,
})

const peers = [risk('BTC/USDT', 40), risk('ETH/USDT', 60), risk('SOL/USDT', 80), risk('AAPL', 20)]

const backtest = (strategy, hold, extra = {}) => ({
  period: { candles: 900 },
  strategy_return_pct: strategy,
  buy_hold_return_pct: hold,
  strategy_max_drawdown_pct: -30,
  buy_hold_max_drawdown_pct: -50,
  trades: { count: 12, win_rate_pct: 42 },
  sample_warning: false,
  ...extra,
})

const base = {
  symbol: 'ETH/USDT',
  name: 'Ethereum',
  tick,
  signals: { '1d': signal('Buy', 38), '1h': signal('Hold', 5) },
  risk: peers[1],
  peers,
  backtest: backtest(80, 20),
}

const text = (brief) => brief.sections.flatMap((s) => s.points).concat(brief.cautions).join(' ')

describe('buildBrief', () => {
  it('opens with the daily rating and how volatile the asset is relative to the others', () => {
    const five = [...peers, risk('XRP/USDT', 100)]            // volatilities 20, 40, 60, 80, 100
    const asset = (symbol, name, entry) => buildBrief({ ...base, symbol, name, risk: entry, peers: five }).headline

    expect(asset('ETH/USDT', 'Ethereum', five[1])).toBe('Ethereum: Buy on the daily chart, moderate volatility relative to the other assets')
    expect(asset('SOL/USDT', 'Solana', five[2])).toContain('high volatility')
    expect(asset('XRP/USDT', 'XRP', five[4])).toContain('high volatility')
    expect(asset('AAPL', 'Apple', five[3])).toContain('low volatility')
    expect(buildBrief({ ...base, peers: [risk('ETH/USDT', 60)] }).headline).not.toContain('volatility')  // too few peers to compare
  })

  it('describes the live move and where the price sits in its 24-hour range', () => {
    const body = text(buildBrief(base))

    expect(body).toContain('down 2.50% over the last 24 hours')
    expect(body).toContain('middle of its 24-hour range')
    expect(text(buildBrief({ ...base, tick: { ...tick, price: 108 } }))).toContain('upper third')
    expect(text(buildBrief({ ...base, tick: { ...tick, price: 92 } }))).toContain('lower third')
  })

  it('reports the votes and the strongest drivers, ignoring neutral rules', () => {
    const body = text(buildBrief(base))

    expect(body).toContain('rate it Buy (score +38')
    expect(body).toContain('3 of 6 rules are bullish, 1 bearish and 2 neutral')
    expect(body).toContain('Price is above the 50-candle average; MACD histogram is positive')
    expect(body).not.toContain('Volume is normal')
  })

  it('says when the two timeframes agree, disagree or have no direction', () => {
    const say = (daily, hourly) => text(buildBrief({ ...base, signals: { '1d': daily, '1h': hourly } }))

    expect(say(signal('Buy', 38), signal('Strong Buy', 60))).toContain('Both timeframes point the same way')
    expect(say(signal('Buy', 38), signal('Sell', -30))).toContain('The two timeframes disagree')
    expect(say(signal('Buy', 38), signal('Hold', 0))).toContain('Only one of the two timeframes has a clear direction')
    expect(say(signal('Hold', 0), signal('Hold', 3))).toContain('Neither timeframe shows a clear direction')
  })

  it('ranks volatility and compares recent against long-run volatility', () => {
    expect(text(buildBrief(base))).toContain('number 2 of 4 by volatility')
    expect(text(buildBrief({ ...base, risk: { ...peers[1], recent_volatility_pct: 90 } }))).toContain('well above its long-run level')
    expect(text(buildBrief({ ...base, risk: { ...peers[1], recent_volatility_pct: 30 } }))).toContain('calmer than usual')
  })

  it('describes drawdown, with a special case for a new high', () => {
    expect(text(buildBrief(base))).toContain('deepest fall from a peak was -50.0%')
    expect(text(buildBrief(base))).toContain('currently 20.0% below its highest close')
    expect(text(buildBrief({ ...base, risk: { ...peers[1], current_drawdown_pct: 0 } }))).toContain('at a new high right now')
  })

  it('states value at risk in plain terms', () => {
    const body = text(buildBrief(base))

    expect(body).toContain('1 day in 20 it has lost 4.00% or more')
    expect(body).toContain('average loss was 6.00%')
    expect(body).toContain('worst single day was -12.00% on 2025-02-10')
  })

  it('compares the backtest with holding, and flags a thin sample', () => {
    expect(text(buildBrief(base))).toContain('They beat holding')
    const trailing = text(buildBrief({ ...base, backtest: backtest(5, 20, { trades: { count: 4, win_rate_pct: 25 }, sample_warning: true }) }))
    expect(trailing).toContain('They trailed holding')
    expect(trailing).toContain('only 4 trades')
    expect(trailing).toContain('did worse than simply holding')
  })

  it('warns about the most volatile assets and ratings near the Buy/Sell line', () => {
    const volatile = buildBrief({ ...base, symbol: 'SOL/USDT', name: 'Solana', risk: peers[2] })
    expect(volatile.cautions.join(' ')).toContain('among the most volatile assets tracked')

    const close = buildBrief({ ...base, signals: { '1d': signal('Buy', 21), '1h': signal('Hold', 5) } })
    expect(close.cautions.join(' ')).toContain('daily rating sits close to the Buy/Sell threshold')
    expect(buildBrief(base).cautions.join(' ')).not.toContain('threshold')
  })

  it('degrades gracefully when pieces of data are missing', () => {
    const empty = buildBrief({ symbol: 'ETH/USDT', name: 'Ethereum', signals: { '1d': null, '1h': null }, risk: null, peers: [], backtest: null })

    expect(empty.headline).toBe('Ethereum: no daily rating yet on the daily chart')
    const body = text(empty)
    expect(body).toContain('Waiting for a live price')
    expect(body).toContain('daily rating is not available')
    expect(body).toContain('Risk figures are not available')
    expect(body).toContain('backtest is not available')
    expect(empty.sections).toHaveLength(4)
  })

  it('treats "insufficient data" as no rating and never claims to be AI-driven', () => {
    const brief = buildBrief({ ...base, signals: { '1d': { rating: 'Insufficient data', score: null }, '1h': signal('Hold', 5) } })

    expect(brief.headline).toContain('no daily rating yet')
    expect(text(brief)).toContain('not enough daily candles')
    expect(brief.note).toContain('not AI')
    expect(brief.note).toContain('not investment advice')
  })
})
