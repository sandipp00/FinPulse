import { formatPrice, getAssetDetails } from './format'
import { ROUTES } from './routes'

// What the notification bell is made of: price alerts the user sets, and changes to a
// daily buy/sell rating. Everything here is pure (no storage, no React), so the rules
// for "when does this fire?" can be tested on their own.

export const MAX_NOTIFICATIONS = 50
export const MAX_ALERTS = 20

const DIRECTIONS = ['above', 'below']

// crypto.randomUUID only exists on secure origins (https or localhost), and this app can
// be served over plain http on a local network, so build an id that works everywhere.
export function newId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

const shortName = (symbol) => symbol.replace('/USDT', '')
const fail = (error) => ({ ok: false, error })

/**
 * Check a new price alert against the live prices. An alert that is already true would
 * fire the instant it is saved, which is never what someone means, so it is refused.
 */
export function validateAlert(input, { ticks, liveSymbols, existing }, now = Date.now()) {
  const { symbol, direction } = input
  const price = Number(input.price)

  if (!liveSymbols.includes(symbol)) return fail('Pick one of the live assets.')
  if (!DIRECTIONS.includes(direction)) return fail('Choose whether the price should go above or below.')
  if (!Number.isFinite(price) || price <= 0) return fail('Enter a price greater than zero.')
  if (existing.length >= MAX_ALERTS) return fail(`You can keep up to ${MAX_ALERTS} active alerts. Remove one first.`)

  const current = ticks[symbol]?.price
  if (current == null) return fail('Still waiting for a live price for that asset. Try again in a moment.')

  const name = shortName(symbol)
  if (direction === 'above' && price <= current) {
    return fail(`${name} is already at ${formatPrice(current, symbol)}, which is above ${formatPrice(price, symbol)}. Choose a higher price.`)
  }
  if (direction === 'below' && price >= current) {
    return fail(`${name} is already at ${formatPrice(current, symbol)}, which is below ${formatPrice(price, symbol)}. Choose a lower price.`)
  }
  if (existing.some((a) => a.symbol === symbol && a.direction === direction && a.price === price)) {
    return fail('You already have that alert.')
  }

  return { ok: true, alert: { id: newId(), symbol, direction, price, createdAt: now } }
}

/** Which alerts have been reached by the latest prices, and which are still waiting. */
export function evaluateAlerts(alerts, ticks) {
  const remaining = []
  const fired = []

  for (const alert of alerts) {
    const price = ticks[alert.symbol]?.price
    const reached = price != null && (alert.direction === 'above' ? price >= alert.price : price <= alert.price)
    if (reached) fired.push({ alert, price })
    else remaining.push(alert)
  }
  return { remaining, fired }
}

/**
 * Compare the latest ratings with the ones last seen. The first time a symbol is seen it
 * is only recorded (there is nothing to compare with), and unrated symbols are ignored.
 */
export function detectRatingChanges(previous, signals) {
  const ratings = { ...previous }
  const changes = []

  for (const signal of signals) {
    if (signal.score == null || !signal.rating) continue
    const before = previous[signal.symbol]
    if (before !== undefined && before !== signal.rating) {
      changes.push({ symbol: signal.symbol, from: before, to: signal.rating })
    }
    ratings[signal.symbol] = signal.rating
  }
  return { ratings, changes }
}

export function alertNotification(alert, price, now = Date.now()) {
  const reached = alert.direction === 'above' ? 'rose to' : 'fell to'
  return {
    id: newId(),
    kind: 'alert',
    ts: now,
    read: false,
    href: ROUTES.markets,
    text: `${getAssetDetails(alert.symbol).name} ${reached} ${formatPrice(price, alert.symbol)}, reaching your alert at ${formatPrice(alert.price, alert.symbol)}.`,
  }
}

export function ratingNotification(change, now = Date.now()) {
  return {
    id: newId(),
    kind: 'signal',
    ts: now,
    read: false,
    href: ROUTES.analytics,
    text: `${getAssetDetails(change.symbol).name}'s daily signal changed from ${change.from} to ${change.to}.`,
  }
}

export const unreadCount = (notifications) => notifications.filter((n) => !n.read).length

/** Newest first, capped, so storage cannot grow without limit. */
export const addNotifications = (list, added) => [...added, ...list].slice(0, MAX_NOTIFICATIONS)
