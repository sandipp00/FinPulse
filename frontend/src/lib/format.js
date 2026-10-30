export const assetDetails = {
  // US stocks (backend/stocks.py), coloured by sector.
  AAPL: { name: 'Apple Inc.', color: '#60A5FA', currency: 'USD' },
  NVDA: { name: 'NVIDIA Corporation', color: '#60A5FA', currency: 'USD' },
  MSFT: { name: 'Microsoft Corporation', color: '#60A5FA', currency: 'USD' },
  GOOGL: { name: 'Alphabet Inc.', color: '#C084FC', currency: 'USD' },
  AMZN: { name: 'Amazon.com, Inc.', color: '#F472B6', currency: 'USD' },
  META: { name: 'Meta Platforms, Inc.', color: '#C084FC', currency: 'USD' },
  TSLA: { name: 'Tesla, Inc.', color: '#F472B6', currency: 'USD' },
  AVGO: { name: 'Broadcom Inc.', color: '#60A5FA', currency: 'USD' },
  LLY: { name: 'Eli Lilly and Company', color: '#2DD4BF', currency: 'USD' },
  'BRK-B': { name: 'Berkshire Hathaway Inc.', color: '#FBBF24', currency: 'USD' },
  WMT: { name: 'Walmart Inc.', color: '#34D399', currency: 'USD' },
  MU: { name: 'Micron Technology, Inc.', color: '#60A5FA', currency: 'USD' },
  JPM: { name: 'JPMorgan Chase & Co.', color: '#FBBF24', currency: 'USD' },
  AMD: { name: 'Advanced Micro Devices, Inc.', color: '#60A5FA', currency: 'USD' },
  V: { name: 'Visa Inc.', color: '#FBBF24', currency: 'USD' },
  XOM: { name: 'ExxonMobil Holdings Corporation', color: '#F97316', currency: 'USD' },
  JNJ: { name: 'Johnson & Johnson', color: '#2DD4BF', currency: 'USD' },
  MA: { name: 'Mastercard Incorporated', color: '#FBBF24', currency: 'USD' },
  ABBV: { name: 'AbbVie Inc.', color: '#2DD4BF', currency: 'USD' },
  CVX: { name: 'Chevron Corporation', color: '#F97316', currency: 'USD' },
  COST: { name: 'Costco Wholesale Corporation', color: '#34D399', currency: 'USD' },
  PLTR: { name: 'Palantir Technologies Inc.', color: '#60A5FA', currency: 'USD' },
  CSCO: { name: 'Cisco Systems, Inc.', color: '#60A5FA', currency: 'USD' },
  KO: { name: 'The Coca-Cola Company', color: '#34D399', currency: 'USD' },
  ORCL: { name: 'Oracle Corporation', color: '#60A5FA', currency: 'USD' },
  PG: { name: 'The Procter & Gamble Company', color: '#34D399', currency: 'USD' },
  MRK: { name: 'Merck & Co., Inc.', color: '#2DD4BF', currency: 'USD' },
  UNH: { name: 'UnitedHealth Group Incorporated', color: '#2DD4BF', currency: 'USD' },
  BAC: { name: 'Bank of America Corporation', color: '#FBBF24', currency: 'USD' },
  INTC: { name: 'Intel Corporation', color: '#60A5FA', currency: 'USD' },
  'BTC/USDT': { name: 'Bitcoin', color: '#F7931A', currency: 'USD' },
  'ETH/USDT': { name: 'Ethereum', color: '#818CF8', currency: 'USD' },
  'SOL/USDT': { name: 'Solana', color: '#2DD4BF', currency: 'USD' },
  'BNB/USDT': { name: 'BNB', color: '#FBBF24', currency: 'USD' },
  'XRP/USDT': { name: 'XRP', color: '#94A3B8', currency: 'USD' },
  'TRX/USDT': { name: 'TRON', color: '#EF4444', currency: 'USD' },
  'HYPE/USDT': { name: 'Hyperliquid', color: '#5EEAD4', currency: 'USD' },
  'ZEC/USDT': { name: 'Zcash', color: '#F4B728', currency: 'USD' },
  'DOGE/USDT': { name: 'Dogecoin', color: '#C2A633', currency: 'USD' },
  'LINK/USDT': { name: 'Chainlink', color: '#375BD2', currency: 'USD' },
  'ADA/USDT': { name: 'Cardano', color: '#3B82F6', currency: 'USD' },
  'XLM/USDT': { name: 'Stellar', color: '#A3A3A3', currency: 'USD' },
  'NEAR/USDT': { name: 'NEAR Protocol', color: '#34D399', currency: 'USD' },
  'BCH/USDT': { name: 'Bitcoin Cash', color: '#8DC351', currency: 'USD' },
  'LTC/USDT': { name: 'Litecoin', color: '#BFBBBB', currency: 'USD' },
  'UNI/USDT': { name: 'Uniswap', color: '#FF007A', currency: 'USD' },
  'AVAX/USDT': { name: 'Avalanche', color: '#E84142', currency: 'USD' },
  'SUI/USDT': { name: 'Sui', color: '#4DA2FF', currency: 'USD' },
  'GRAM/USDT': { name: 'Gram (Toncoin)', color: '#0098EA', currency: 'USD' },
  'HBAR/USDT': { name: 'Hedera', color: '#9CA3AF', currency: 'USD' },
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
  '^RUT': { name: 'Russell 2000', color: '#C084FC', currency: 'USD' },
  '^NYA': { name: 'NYSE Composite', color: '#7DD3FC', currency: 'USD' },
  // The VIX is in volatility points, not a price: no currency symbol.
  '^VIX': { name: 'VIX', color: '#F43F5E', currency: null },
  '^MXX': { name: 'S&P/BMV IPC', color: '#34D399', currency: 'MXN' },
  '^STOXX': { name: 'STOXX Europe 600', color: '#A5B4FC', currency: 'EUR' },
  '^IBEX': { name: 'IBEX 35', color: '#FCA5A5', currency: 'EUR' },
  'FTSEMIB.MI': { name: 'FTSE MIB', color: '#86EFAC', currency: 'EUR' },
  '^AEX': { name: 'AEX', color: '#FDBA74', currency: 'EUR' },
  '^SSMI': { name: 'SMI', color: '#F87171', currency: 'CHF' },
  '^OMX': { name: 'OMX Stockholm 30', color: '#60A5FA', currency: 'SEK' },
  '399001.SZ': { name: 'Shenzhen Component', color: '#FB923C', currency: 'CNY' },
  '^TWII': { name: 'Taiwan Weighted', color: '#5EEAD4', currency: 'TWD' },
  '^BSESN': { name: 'Sensex', color: '#2DD4BF', currency: 'INR' },
  '^NSEBANK': { name: 'Nifty Bank', color: '#4ADE80', currency: 'INR' },
  '^STI': { name: 'Straits Times', color: '#F472B6', currency: 'SGD' },
  '^JKSE': { name: 'Jakarta Composite', color: '#FCD34D', currency: 'IDR' },
  '^KLSE': { name: 'FTSE Bursa Malaysia KLCI', color: '#93C5FD', currency: 'MYR' },
  '^NZ50': { name: 'S&P/NZX 50', color: '#A3E635', currency: 'NZD' },
  '^TA125.TA': { name: 'TA-125', color: '#67E8F9', currency: 'ILS' },
  '^TASI.SR': { name: 'Tadawul All Share', color: '#22C55E', currency: 'SAR' },
  '^J200.JO': { name: 'FTSE/JSE Top 40', color: '#EAB308', currency: 'ZAR' },
  'GC=F': { name: 'Gold', color: '#EAB308', currency: 'USD' },
  'SI=F': { name: 'Silver', color: '#CBD5E1', currency: 'USD' },
  'XAU/USDT': { name: 'Gold (live)', color: '#EAB308', currency: 'USD' },
  'XAG/USDT': { name: 'Silver (live)', color: '#CBD5E1', currency: 'USD' },
  'CL/USDT': { name: 'WTI crude (live)', color: '#F59E0B', currency: 'USD' },
  'BZ/USDT': { name: 'Brent crude (live)', color: '#FB923C', currency: 'USD' },
  'CL=F': { name: 'WTI crude (futures)', color: '#F59E0B', currency: 'USD' },
  'BZ=F': { name: 'Brent crude (futures)', color: '#FB923C', currency: 'USD' },
  'USD/INR': { name: 'US dollar / Indian rupee', color: '#94A3B8', currency: 'INR' },
  'EUR/USD': { name: 'Euro / US dollar', color: '#94A3B8', currency: 'USD' },
  'GBP/USD': { name: 'Pound / US dollar', color: '#94A3B8', currency: 'USD' },
  'USD/JPY': { name: 'US dollar / Japanese yen', color: '#94A3B8', currency: 'JPY' },
  'EUR/INR': { name: 'Euro / Indian rupee', color: '#94A3B8', currency: 'INR' },
  'EUR/GBP': { name: 'Euro / pound', color: '#94A3B8', currency: 'GBP' },
  'EUR/JPY': { name: 'Euro / Japanese yen', color: '#94A3B8', currency: 'JPY' },
}

// The followed cryptocurrencies, largest market cap first (matches LIVE_SYMBOLS).
export const CRYPTO_RANK = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'SOL/USDT', 'TRX/USDT', 'HYPE/USDT', 'ZEC/USDT', 'DOGE/USDT', 'LINK/USDT', 'ADA/USDT', 'XLM/USDT', 'NEAR/USDT', 'BCH/USDT', 'LTC/USDT', 'UNI/USDT', 'AVAX/USDT', 'SUI/USDT', 'GRAM/USDT', 'HBAR/USDT']

/** Live crypto symbols in market-cap order; unknown ones keep their order after the ranked ones. */
export function byCryptoRank(symbols) {
  const rank = (symbol) => {
    const i = CRYPTO_RANK.indexOf(symbol)
    return i === -1 ? CRYPTO_RANK.length : i
  }
  return [...symbols].sort((a, b) => rank(a) - rank(b))
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
    // No currency (e.g. the VIX, in points): a plain number.
    priceFormatters.set(key, new Intl.NumberFormat('en-US', {
      ...(currency ? { style: 'currency', currency } : { style: 'decimal' }),
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
