// Which live source a tick came from: 'crypto' (Binance spot), 'tradfi' (Binance
// gold, silver and oil futures) or 'quotes' (Yahoo stocks, indices and FX).

/** The market a tick belongs to; ticks without one are crypto. */
export function marketOf(tick) {
  return tick?.market ?? 'crypto'
}

/** Symbols in `ticks` that belong to `market`, in the order they first arrived. */
export function symbolsInMarket(ticks, market) {
  return Object.keys(ticks).filter((symbol) => marketOf(ticks[symbol]) === market)
}
