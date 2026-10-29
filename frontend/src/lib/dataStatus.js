// How fresh a number on screen is. Every price the shell shows carries one of
// these, so a stored close is never mistaken for a live quote.
//
//   live        a tick from the exchange feed, received recently, feed connected
//   stale       a live symbol whose last tick is too old, or the feed is down
//   historical  the latest close stored in SQLite (daily history)
//   cached      a provider response kept after the provider started failing
//   unavailable nothing to show

// Same threshold the backend uses to call the exchange feed stale (backend/live.py).
export const STALE_AFTER_MS = 30_000

export const DATA_STATUS_BADGE = {
  live: 'LIVE',
  stale: 'STALE',
  historical: 'HIST',
  cached: 'CACHED',
  unavailable: 'N/A',
}

export const DATA_STATUS_LABEL = {
  live: 'Live from the exchange feed',
  stale: 'Last live price, no recent update',
  historical: 'Latest stored daily close, not a live quote',
  cached: 'Kept from an earlier response; the provider is not answering',
  unavailable: 'No data available',
}

/** Status of a live tick (see useLivePrices), given the socket status and the current time in ms. */
export function tickStatus(tick, feedStatus, now) {
  if (!tick || tick.price == null || !Number.isFinite(Number(tick.price))) return 'unavailable'
  if (feedStatus !== 'live') return 'stale'
  const seenAt = Number(tick.seenAt)
  if (!Number.isFinite(seenAt) || now - seenAt > STALE_AFTER_MS) return 'stale'
  return 'live'
}

/** Status of a stored asset from /api/assets. */
export function storedStatus(asset) {
  if (!asset || asset.latest_price == null || !Number.isFinite(Number(asset.latest_price))) return 'unavailable'
  return 'historical'
}

/** Parse the timestamps the API returns ("2026-10-14 00:00:00+00:00", ISO strings, unix ms), or a Date. */
export function parseTimestamp(value) {
  if (value == null || value === '') return null
  const date = value instanceof Date || typeof value === 'number'
    ? new Date(value)
    : new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(date.getTime()) ? null : date
}

const DAY_MS = 86_400_000

/** Whole days between a timestamp and now (0 for today or the future), or null if unknown. */
export function ageInDays(value, now) {
  const date = parseTimestamp(value)
  if (!date) return null
  return Math.max(0, Math.floor((now - date.getTime()) / DAY_MS))
}

const shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const longDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })

/** "14 Oct" (or "14 Oct 2026" with `withYear`), in UTC since stored bars are UTC days; "—" if unknown. */
export function formatAsOfDate(value, { withYear = false } = {}) {
  const date = parseTimestamp(value)
  if (!date) return '—'
  return (withYear ? longDate : shortDate).format(date)
}

/** "3s ago", "4m ago", "2h ago", "5d ago"; "—" if unknown. */
export function formatAge(ms) {
  if (ms == null || !Number.isFinite(ms)) return '—'
  const seconds = Math.max(0, Math.round(ms / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86_400)}d ago`
}

/** The newest `latest_timestamp` across stored assets: when the stored history ends. */
export function latestStoredTimestamp(assets) {
  let newest = null
  for (const asset of assets ?? []) {
    const date = parseTimestamp(asset.latest_timestamp)
    if (date && (!newest || date > newest)) newest = date
  }
  return newest
}

/**
 * One-word state of the backend for the top bar, from the polled health check:
 * 'checking' before the first answer, 'ok', or 'error'.
 */
export function apiState({ health, healthError, loading }) {
  if (healthError) return 'error'
  if (health?.status === 'healthy') return 'ok'
  return loading ? 'checking' : 'error'
}

const PROVIDER_NAME = { binance: 'Binance', database: 'Local database' }
const clockTime = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC' })

/**
 * One line describing where a series came from, from the `meta` the API attaches
 * (backend/schemas/market.py SourceMeta). Null when there is no meta.
 */
export function describeSource(meta) {
  if (!meta) return null
  const provider = PROVIDER_NAME[meta.provider] ?? meta.provider
  const fetched = parseTimestamp(meta.retrieved_at)
  const newest = parseTimestamp(meta.source_timestamp)
  return [
    meta.endpoint ? `${provider} (${meta.endpoint})` : provider,
    fetched && `fetched ${clockTime.format(fetched)} UTC`,
    newest && `latest bar ${clockTime.format(newest)} UTC`,
  ].filter(Boolean).join(' · ')
}

/** True when the API says the series is a kept response, not a fresh one. */
export function isCachedFallback(meta) {
  return meta?.status === 'cached'
}
