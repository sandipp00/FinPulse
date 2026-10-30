// Pure helpers for the instrument explorer: search, bar-count options, return
// statistics, comparison alignment and the page's URL state.

import { getAssetDetails } from './format'

/** Instruments matching a search, best first: exact symbol, then prefix, then anywhere in symbol or name. */
export function searchInstruments(instruments, query) {
  const q = (query ?? '').trim().toLowerCase()
  if (!q) return instruments
  const scored = []
  for (const item of instruments) {
    const symbol = item.symbol.toLowerCase()
    const bare = symbol.replace(/^\^/, '').split('/')[0]
    const name = getAssetDetails(item.symbol).name.toLowerCase()
    let score = null
    if (symbol === q || bare === q) score = 0
    else if (symbol.startsWith(q) || bare.startsWith(q)) score = 1
    else if (name.startsWith(q)) score = 2
    else if (symbol.includes(q) || name.includes(q)) score = 3
    if (score != null) scored.push([score, item])
  }
  return scored.sort((a, b) => a[0] - b[0]).map(([, item]) => item)
}

// The API's limits: the exchange serves 50-1000 candles, stored history up to 5000 daily bars.
const EXCHANGE_LIMITS = [100, 250, 500, 1000]
const STORED_LIMITS = [90, 250, 500, 5000]

/** Which source a request will use, mirroring the API's `source=auto`. */
export function sourceFor(instrument) {
  return instrument?.live ? 'binance' : 'database'
}

export function limitOptions(source) {
  return source === 'binance' ? EXCHANGE_LIMITS : STORED_LIMITS
}

export function limitLabel(limit) {
  return limit >= 5000 ? 'All' : `${limit} bars`
}

/** Units the volume figure is counted in, or null when the source does not report volume. */
export function volumeUnit(instrument) {
  if (!instrument || instrument.asset_class === 'fx') return null  // Yahoo reports no FX volume
  // Exchange pairs (crypto, live gold and silver) count volume in the base asset.
  if (instrument.symbol.includes('/')) return instrument.symbol.split('/')[0]
  if (instrument.asset_class === 'stock') return 'shares'
  if (instrument.asset_class === 'commodity') return 'contracts'
  return null
}

/** Simple return of each bar's close over the previous close, in percent. */
export function barReturns(candles) {
  const returns = []
  for (let i = 1; i < candles.length; i += 1) {
    const previous = candles[i - 1].close
    if (previous > 0) returns.push({ time: candles[i].time, value: (candles[i].close / previous - 1) * 100 })
  }
  return returns
}

/** Headline figures for a series of candles; null if there are fewer than two bars. */
export function summarizeReturns(candles) {
  if (!candles || candles.length < 2) return null
  const first = candles[0]
  const last = candles.at(-1)
  const returns = barReturns(candles).map((point) => point.value)
  const volumes = candles.map((candle) => candle.volume)
  const volumeReported = volumes.some((volume) => volume > 0)
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length
  const variance = returns.length > 1
    ? returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1)
    : null

  return {
    bars: candles.length,
    firstTime: first.time,
    lastTime: last.time,
    firstClose: first.close,
    lastClose: last.close,
    periodReturnPct: (last.close / first.close - 1) * 100,
    logReturnPct: Math.log(last.close / first.close) * 100,
    bestBarPct: Math.max(...returns),
    worstBarPct: Math.min(...returns),
    barVolatilityPct: variance == null ? null : Math.sqrt(variance),
    high: Math.max(...candles.map((candle) => candle.high)),
    low: Math.min(...candles.map((candle) => candle.low)),
    volumeReported,
    averageVolume: volumeReported ? volumes.reduce((sum, value) => sum + value, 0) / volumes.length : null,
  }
}

const DAY = 86_400

/**
 * Two series on the timestamps they share, both rebased to 100 at the first shared
 * point. Daily bars are matched by UTC calendar day (sources stamp days differently);
 * intraday bars by exact time. Points only one series has are dropped, not filled.
 */
export function alignForComparison(primary, other, interval) {
  const keyOf = interval === '1d' ? (time) => Math.floor(time / DAY) : (time) => time
  const others = new Map(other.map((candle) => [keyOf(candle.time), candle]))
  const shared = []
  for (const candle of primary) {
    const match = others.get(keyOf(candle.time))
    if (match && candle.close > 0 && match.close > 0) shared.push([candle, match])
  }
  if (shared.length < 2) return { points: [], shared: shared.length, primaryReturnPct: null, otherReturnPct: null }

  const [baseA, baseB] = shared[0]
  const points = shared.map(([a, b]) => ({
    time: a.time,
    primary: (a.close / baseA.close) * 100,
    other: (b.close / baseB.close) * 100,
  }))
  const last = points.at(-1)
  return {
    points,
    shared: shared.length,
    primaryReturnPct: last.primary - 100,
    otherReturnPct: last.other - 100,
  }
}

/** The explorer's state as stored in the URL (?symbol=&interval=&limit=&compare=). */
export function parseExplorerQuery(search) {
  const params = new URLSearchParams(search ?? '')
  const limit = Number(params.get('limit'))
  return {
    symbol: params.get('symbol') || '',
    interval: params.get('interval') || '',
    limit: Number.isInteger(limit) && limit > 0 ? limit : null,
    compare: params.get('compare') || '',
  }
}

export function buildExplorerQuery({ symbol, interval, limit, compare }) {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  if (interval) params.set('interval', interval)
  if (limit) params.set('limit', String(limit))
  if (compare) params.set('compare', compare)
  const text = params.toString()
  return text ? `?${text}` : ''
}

/**
 * Make a requested state valid for the chosen instrument: an interval it supports
 * (daily otherwise), a bar count its source allows, and a comparison instrument
 * that is a different instrument offering the same interval.
 */
export function resolveExplorerState(requested, instruments) {
  const bySymbol = new Map(instruments.map((item) => [item.symbol, item]))
  const instrument = bySymbol.get(requested.symbol) ?? instruments[0] ?? null
  if (!instrument) return null

  const interval = instrument.intervals.includes(requested.interval) ? requested.interval : '1d'
  const options = limitOptions(sourceFor(instrument))
  const limit = options.includes(requested.limit) ? requested.limit : options[2]
  const other = bySymbol.get(requested.compare)
  const compare = other && other.symbol !== instrument.symbol && other.intervals.includes(interval)
    ? other.symbol
    : ''

  return { instrument, symbol: instrument.symbol, interval, limit, compare }
}

const quoteFormatters = new Map()

/**
 * A price in the currency the API says it is quoted in. ISO currencies get their
 * symbol ("$345.79", "₹22,622.70"); anything else is written out ("80,911.96 USDT").
 */
export function formatQuote(value, currency) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  const digits = Math.abs(number) < 10 ? 4 : 2
  const key = `${currency}|${digits}`
  if (!quoteFormatters.has(key)) {
    let formatter
    try {
      formatter = new Intl.NumberFormat('en-US', { style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: digits })
      // Intl accepts any three letters; only trust codes it knows a symbol for.
      if (formatter.formatToParts(1).find((part) => part.type === 'currency')?.value === currency) formatter = null
    } catch {
      formatter = null
    }
    quoteFormatters.set(key, formatter
      ? { formatter, suffix: '' }
      : {
          formatter: new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: digits }),
          suffix: currency ? ` ${currency}` : '',
        })
  }
  const { formatter, suffix } = quoteFormatters.get(key)
  return `${formatter.format(number)}${suffix}`
}

const dayFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const timeFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

/** A bar's time (unix seconds): the date for daily bars, date and time (UTC) otherwise. */
export function formatBarTime(seconds, interval) {
  if (seconds == null) return '—'
  const date = new Date(seconds * 1000)
  return interval === '1d' ? dayFormat.format(date) : `${timeFormat.format(date)} UTC`
}
