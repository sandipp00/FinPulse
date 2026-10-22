export const assetDetails = {
  AAPL: { name: 'Apple Inc.', color: '#A5B4FC', currency: 'USD' },
  'BTC/USDT': { name: 'Bitcoin', color: '#F7931A', currency: 'USD' },
  'ETH/USDT': { name: 'Ethereum', color: '#818CF8', currency: 'USD' },
  'SOL/USDT': { name: 'Solana', color: '#2DD4BF', currency: 'USD' },
  'BNB/USDT': { name: 'BNB', color: '#FBBF24', currency: 'USD' },
  'XRP/USDT': { name: 'XRP', color: '#94A3B8', currency: 'USD' },
  '^NSEI': { name: 'Nifty 50', color: '#34D399', currency: 'INR' },
}

export function getAssetDetails(symbol) {
  return assetDetails[symbol] ?? {
    name: symbol,
    color: '#94A3B8',
    currency: 'USD',
  }
}

export function formatPrice(value, symbol) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  // Sub-$10 assets (XRP, small caps) need more precision than cents.
  const digits = Math.abs(number) < 10 ? 4 : 2

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: getAssetDetails(symbol).currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: digits,
  }).format(number)
}

export function formatPercent(value, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${number.toFixed(digits)}%`
}

export function formatCompact(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(Number(value))
}
