import { describe, expect, it } from 'vitest'
import { estimateOrder, valuePortfolio } from './portfolio'

const portfolio = {
  account: { starting_cash: 100_000, cash: 90_000 },
  totals: { realized_pnl: 12, fees_paid: 5 },
  positions: [
    { symbol: 'BTC/USDT', quantity: 0.2, avg_cost: 50_000, price: 50_000 },
    { symbol: 'ETH/USDT', quantity: 4, avg_cost: 2_500, price: 2_500 },
  ],
}

describe('valuePortfolio', () => {
  it('returns null until a portfolio has loaded', () => {
    expect(valuePortfolio(null, {})).toBeNull()
  })

  it('re-values positions with live ticks and falls back to the server price', () => {
    const view = valuePortfolio(portfolio, { 'BTC/USDT': { price: 55_000 } })

    const [btc, eth] = view.positions
    expect(btc).toMatchObject({ price: 55_000, live: true, market_value: 11_000 })
    expect(btc.unrealized_pnl).toBeCloseTo(1_000)
    expect(btc.unrealized_pnl_pct).toBeCloseTo(10)
    expect(eth).toMatchObject({ price: 2_500, live: false, unrealized_pnl: 0 })
  })

  it('computes equity, P&L, return and weights from cash plus positions', () => {
    const view = valuePortfolio(portfolio, { 'BTC/USDT': { price: 55_000 } })

    expect(view.totals.equity).toBeCloseTo(90_000 + 11_000 + 10_000)
    expect(view.totals.total_pnl).toBeCloseTo(11_000)
    expect(view.totals.total_return_pct).toBeCloseTo(11)
    expect(view.totals.unrealized_pnl).toBeCloseTo(1_000)
    expect(view.totals.realized_pnl).toBe(12) // untouched server figure
    expect(view.positions[0].weight_pct).toBeCloseTo((11_000 / 111_000) * 100)
  })

  it('does not mutate the input', () => {
    valuePortfolio(portfolio, { 'BTC/USDT': { price: 99 } })
    expect(portfolio.positions[0].price).toBe(50_000)
  })
})

describe('estimateOrder', () => {
  const base = { price: 50_000, cash: 10_000, heldQuantity: 2, feeRate: 0.001 }

  it('sizes a USD buy so that cost plus fee equals the amount', () => {
    const estimate = estimateOrder({ ...base, side: 'buy', size: { kind: 'usd', value: 1_000 } })

    expect(estimate.notional + estimate.fee).toBeCloseTo(1_000)
  })

  it('sizes a percent buy from cash and a percent sell from the position', () => {
    const buy = estimateOrder({ ...base, side: 'buy', size: { kind: 'percent', value: 50 } })
    const sell = estimateOrder({ ...base, side: 'sell', size: { kind: 'percent', value: 25 } })

    expect(buy.notional + buy.fee).toBeCloseTo(5_000)
    expect(sell.quantity).toBeCloseTo(0.5)
  })

  it('returns null without a price or a positive size', () => {
    expect(estimateOrder({ ...base, price: undefined, side: 'buy', size: { kind: 'usd', value: 5 } })).toBeNull()
    expect(estimateOrder({ ...base, side: 'buy', size: { kind: 'usd', value: 0 } })).toBeNull()
    expect(estimateOrder({ ...base, side: 'buy', size: null })).toBeNull()
  })
})
