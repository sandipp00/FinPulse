// Live gold and silver: Binance USD-M perpetual futures, which trade around the
// clock while the gold and silver markets they track do not.

const nyParts = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  hour: 'numeric',
  hourCycle: 'h23',
})

/** True for a tick from the live metals feed (as opposed to crypto). */
export function isLiveMetal(tick) {
  return tick?.asset_class === 'commodity'
}

/**
 * Whether COMEX gold and silver futures are trading at `date`: Sunday 18:00 to
 * Friday 17:00 New York time, with a daily break from 17:00 to 18:00. Exchange
 * holidays are not known here, so on a holiday this still says open.
 */
export function metalsMarketOpen(date) {
  const parts = Object.fromEntries(nyParts.formatToParts(date).map((part) => [part.type, part.value]))
  const hour = Number(parts.hour)
  const day = parts.weekday
  if (day === 'Sat') return false
  if (day === 'Sun') return hour >= 18
  if (day === 'Fri') return hour < 17
  return hour !== 17
}
