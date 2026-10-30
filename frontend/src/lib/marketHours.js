// Pure helpers for the market hours page. Times are unix seconds.

/** Whether a session is open at `now`, and how long until that changes. */
export function sessionStatus(session, now) {
  if (!session) return { state: 'unknown', seconds: null }
  if (now < session.start) return { state: 'closed', seconds: session.start - now, estimated: session.estimated }
  if (now < session.end) return { state: 'open', seconds: session.end - now, estimated: session.estimated }
  return { state: 'closed', seconds: null, estimated: session.estimated }
}

/** "2h 14m", "45m", "3d 4h" — rounded down to the minute. */
export function formatCountdown(seconds) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'
  const minutes = Math.floor(seconds / 60)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m`
}

/** Where a session sits in a time window, as percentages of its width; null if outside. */
export function sessionBar(session, windowStart, windowEnd) {
  if (!session) return null
  const start = Math.max(session.start, windowStart)
  const end = Math.min(session.end, windowEnd)
  if (end <= start) return null
  const span = windowEnd - windowStart
  return { left: ((start - windowStart) / span) * 100, width: ((end - start) / span) * 100 }
}

/** Open exchanges first (closing soonest first), then the rest by how soon they open. */
export function sortExchanges(exchanges, now) {
  const key = (exchange) => {
    const status = sessionStatus(exchange.session, now)
    if (status.state === 'open') return [0, status.seconds]
    if (status.seconds != null) return [1, status.seconds]
    return [2, 0]
  }
  return [...exchanges].sort((a, b) => {
    const [ga, va] = key(a)
    const [gb, vb] = key(b)
    return ga - gb || va - vb
  })
}

/** FX trades from Sunday 17:00 to Friday 17:00 New York time. */
export function fxMarketOpen(date) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', weekday: 'short', hour: 'numeric', hourCycle: 'h23',
  }).formatToParts(date).map((part) => [part.type, part.value]))
  const hour = Number(parts.hour)
  if (parts.weekday === 'Sat') return false
  if (parts.weekday === 'Sun') return hour >= 17
  if (parts.weekday === 'Fri') return hour < 17
  return true
}
