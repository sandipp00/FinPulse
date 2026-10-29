// Helpers for the News and Calendar pages (see backend/news_api.py).

export const TOPIC_LABEL = {
  rates: 'Rates',
  macro: 'Macro',
  fx: 'FX',
  crypto: 'Crypto',
  filings: 'Filings',
  equities: 'Equities',
}

/** Items matching every chosen filter; an empty filter matches everything. */
export function filterNews(items, { topic = '', instrument = '', source = '' } = {}) {
  return items.filter((item) => (
    (!topic || item.topics.includes(topic))
    && (!instrument || item.instruments.includes(instrument))
    && (!source || item.source === source)
  ))
}

/** Only absolute http(s) links are rendered; anything else is shown as plain text. */
export function safeHref(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null
}

/** Calendar events grouped by date, in date order: [[date, events], ...]. */
export function groupByDate(events) {
  const groups = new Map()
  for (const event of events) {
    if (!groups.has(event.date)) groups.set(event.date, [])
    groups.get(event.date).push(event)
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))
}

const weekdayFormat = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const timeFormat = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })

export function formatEventDate(isoDate) {
  return weekdayFormat.format(new Date(`${isoDate}T00:00:00Z`))
}

/** "12:30 UTC" when the source publishes a time, otherwise null (never guessed). */
export function formatEventTime(timeUtc) {
  if (!timeUtc) return null
  const date = new Date(timeUtc)
  return Number.isNaN(date.getTime()) ? null : `${timeFormat.format(date)} UTC`
}

export const STATUS_LABEL = { past: 'Past', today: 'Today', scheduled: 'Scheduled' }
