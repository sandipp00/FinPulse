/**
 * Re-value a server portfolio with the latest live ticks so P&L moves in real
 * time without polling. The server only supplies quantities, cost basis and
 * cash; every price-dependent number is recomputed here.
 */
export function valuePortfolio(portfolio, ticks) {
  if (!portfolio) return null

  const { account, totals } = portfolio

  const positions = portfolio.positions.map((position) => {
    const live = ticks[position.symbol]?.price
    const price = live ?? position.price
    const marketValue = position.quantity * price
    const pnl = position.quantity * (price - position.avg_cost)

    return {
      ...position,
      price,
      live: live != null,
      market_value: marketValue,
      unrealized_pnl: pnl,
      unrealized_pnl_pct: position.avg_cost ? (price / position.avg_cost - 1) * 100 : null,
    }
  })

  const positionsValue = positions.reduce((sum, p) => sum + p.market_value, 0)
  const equity = account.cash + positionsValue

  return {
    ...portfolio,
    positions: positions.map((p) => ({
      ...p,
      weight_pct: equity ? (p.market_value / equity) * 100 : 0,
    })),
    totals: {
      ...totals,
      cash: account.cash,
      positions_value: positionsValue,
      equity,
      total_pnl: equity - account.starting_cash,
      total_return_pct: (equity / account.starting_cash - 1) * 100,
      unrealized_pnl: positions.reduce((sum, p) => sum + p.unrealized_pnl, 0),
    },
  }
}

/**
 * What an order would roughly do, for the ticket preview. `size` is either
 * { kind: 'usd', value } or { kind: 'percent', value }. Returns null when the
 * inputs can't produce an estimate.
 */
export function estimateOrder({ side, size, price, cash, heldQuantity, feeRate }) {
  if (!price || !size || !(size.value > 0)) return null

  let quantity
  if (side === 'buy') {
    const budget = size.kind === 'usd' ? size.value : (cash * size.value) / 100
    quantity = budget / (price * (1 + feeRate))
  } else if (size.kind === 'percent') {
    quantity = (heldQuantity * size.value) / 100
  } else {
    quantity = size.value / price
  }

  const notional = quantity * price
  return { quantity, notional, fee: notional * feeRate }
}
