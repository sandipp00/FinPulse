export const assetDetails = {
  AAPL: { name: 'Apple Inc.', color: '#A5B4FC', currency: 'USD' },
  'BTC/USDT': { name: 'Bitcoin', color: '#F7931A', currency: 'USD' },
  'ETH/USDT': { name: 'Ethereum', color: '#818CF8', currency: 'USD' },
  'SOL/USDT': { name: 'Solana', color: '#2DD4BF', currency: 'USD' },
  'BNB/USDT': { name: 'BNB', color: '#FBBF24', currency: 'USD' },
  'XRP/USDT': { name: 'XRP', color: '#94A3B8', currency: 'USD' },
  '^NSEI': { name: 'Nifty 50', color: '#34D399', currency: 'INR' },
  '^GSPC': { name: 'S&P 500', color: '#F472B6', currency: 'USD' },
  '^DJI': { name: 'Dow Jones', color: '#60A5FA', currency: 'USD' },
  '^IXIC': { name: 'Nasdaq Composite', color: '#22D3EE', currency: 'USD' },
  '^GSPTSE': { name: 'S&P/TSX Composite', color: '#F87171', currency: 'CAD' },
  '^BVSP': { name: 'Ibovespa', color: '#4ADE80', currency: 'BRL' },
  '^FTSE': { name: 'FTSE 100', color: '#A78BFA', currency: 'GBP' },
  '^GDAXI': { name: 'DAX', color: '#FACC15', currency: 'EUR' },
  '^FCHI': { name: 'CAC 40', color: '#93C5FD', currency: 'EUR' },
  '^STOXX50E': { name: 'Euro Stoxx 50', color: '#818CF8', currency: 'EUR' },
  '^N225': { name: 'Nikkei 225', color: '#FB7185', currency: 'JPY' },
  '^HSI': { name: 'Hang Seng', color: '#F97316', currency: 'HKD' },
  '000001.SS': { name: 'Shanghai Composite', color: '#EF4444', currency: 'CNY' },
  '^KS11': { name: 'KOSPI', color: '#38BDF8', currency: 'KRW' },
  '^AXJO': { name: 'S&P/ASX 200', color: '#FBBF24', currency: 'AUD' },
  'GC=F': { name: 'Gold', color: '#EAB308', currency: 'USD' },
  'SI=F': { name: 'Silver', color: '#CBD5E1', currency: 'USD' },
  'XAU/USDT': { name: 'Gold (live)', color: '#EAB308', currency: 'USD' },
  'XAG/USDT': { name: 'Silver (live)', color: '#CBD5E1', currency: 'USD' },
  'CL/USDT': { name: 'WTI crude (live)', color: '#F59E0B', currency: 'USD' },
  'BZ/USDT': { name: 'Brent crude (live)', color: '#FB923C', currency: 'USD' },
  'USD/INR': { name: 'US dollar / Indian rupee', color: '#94A3B8', currency: 'INR' },
  'EUR/USD': { name: 'Euro / US dollar', color: '#94A3B8', currency: 'USD' },
  'GBP/USD': { name: 'Pound / US dollar', color: '#94A3B8', currency: 'USD' },
  'USD/JPY': { name: 'US dollar / Japanese yen', color: '#94A3B8', currency: 'JPY' },
  'EUR/INR': { name: 'Euro / Indian rupee', color: '#94A3B8', currency: 'INR' },
  'EUR/GBP': { name: 'Euro / pound', color: '#94A3B8', currency: 'GBP' },
  'EUR/JPY': { name: 'Euro / Japanese yen', color: '#94A3B8', currency: 'JPY' },
}

export function getAssetDetails(symbol) {
  return assetDetails[symbol] ?? {
    name: symbol,
    color: '#94A3B8',
    currency: 'USD',
  }
}

// Building an Intl.NumberFormat is slow, and prices are formatted hundreds of
// times per second while ticks stream in, so build each variant once.
const priceFormatters = new Map()

function priceFormatter(currency, digits) {
  const key = `${currency}|${digits}`
  if (!priceFormatters.has(key)) {
    priceFormatters.set(key, new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: digits,
    }))
  }
  return priceFormatters.get(key)
}

export function formatPrice(value, symbol) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  // Sub-$10 assets (XRP, small caps) need more precision than cents.
  const digits = Math.abs(number) < 10 ? 4 : 2

  return priceFormatter(getAssetDetails(symbol).currency, digits).format(number)
}

export function formatPercent(value, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${number.toFixed(digits)}%`
}

const compactFormat = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 })

export function formatCompact(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return compactFormat.format(Number(value))
}
