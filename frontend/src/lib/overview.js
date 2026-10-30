// The Overview page: a cross-asset board, the biggest movers, open markets and coverage.
import { sessionStatus } from './marketHours'

// Benchmarks per board panel, by symbol on the price socket, with a short label for the board.
export const BOARD = [
  { title: 'United States', symbols: ['^GSPC', '^IXIC', '^DJI', '^VIX'] },
  { title: 'Europe', symbols: ['^STOXX50E', '^FTSE', '^GDAXI', '^FCHI'] },
  { title: 'Asia-Pacific', symbols: ['^N225', '^HSI', '000001.SS', '^NSEI'] },
  { title: 'FX', symbols: ['EUR/USD', 'USD/JPY', 'GBP/USD', 'USD/INR'] },
  { title: 'Commodities', symbols: ['XAU/USDT', 'XAG/USDT', 'CL/USDT', 'BZ/USDT'] },
  { title: 'Crypto', symbols: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT'] },
]
const SHORT = {
  '^IXIC': 'Nasdaq', '^STOXX50E': 'Stoxx 50', '^N225': 'Nikkei', '000001.SS': 'Shanghai',
  'XAU/USDT': 'Gold', 'XAG/USDT': 'Silver', 'CL/USDT': 'WTI crude', 'BZ/USDT': 'Brent crude',
}

/** The board's label: a short name, the pair itself for FX, otherwise the asset's name. */
export function boardLabel(symbol, name) {
  if (SHORT[symbol]) return SHORT[symbol]
  if (/^[A-Z]{3}\/[A-Z]{3}$/.test(symbol)) return symbol
  return name
}

// Movers are ranked among these classes: indices and FX move too little to compare.
const MOVER_CLASSES = new Set(['stock', 'crypto', 'commodity'])

/**
 * The biggest gainers and losers among stocks, crypto and commodities, by their
 * day change (24 hours for crypto and the Binance futures, since the previous close
 * for stocks). Each list holds at most `count` and only moves in its direction.
 */
export function movers(ticks, count = 5) {
  const moves = Object.values(ticks)
    .filter((tick) => MOVER_CLASSES.has(tick.asset_class) && Number.isFinite(Number(tick.change_pct_24h)))
    .map((tick) => ({ symbol: tick.symbol, assetClass: tick.asset_class, change: Number(tick.change_pct_24h), window: tick.change_window ?? '24h' }))
    .sort((a, b) => b.change - a.change)
  return {
    gainers: moves.filter((m) => m.change > 0).slice(0, count),
    losers: moves.filter((m) => m.change < 0).reverse().slice(0, count),
  }
}

/** Which exchanges are open at `now` (unix seconds), and the next one to open. */
export function marketsOpen(exchanges, now) {
  const open = []
  let next = null
  for (const exchange of exchanges ?? []) {
    const status = sessionStatus(exchange.session, now)
    if (status.state === 'open') open.push(exchange)
    else if (status.seconds != null && (next == null || status.seconds < next.seconds)) next = { exchange, seconds: status.seconds }
  }
  return { open, next, total: (exchanges ?? []).length }
}

/** How many instruments FinPulse follows in each class, from the asset registry. */
export function coverage(registry) {
  const counts = {}
  for (const asset of registry ?? []) counts[asset.asset_class] = (counts[asset.asset_class] ?? 0) + 1
  return counts
}
