// Live gold, silver and oil: Binance USD-M perpetual futures, which trade around the
// clock while the futures markets they track do not.

const nyParts = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  hour: 'numeric',
  hourCycle: 'h23',
})

/**
 * Whether CME gold, silver and WTI futures are trading at `date`: Sunday 18:00 to
 * Friday 17:00 New York time, with a daily break from 17:00 to 18:00. ICE Brent's
 * hours are close to these. Exchange holidays are not known here, so on a holiday
 * this still says open.
 */
export function futuresMarketOpen(date) {
  const parts = Object.fromEntries(nyParts.formatToParts(date).map((part) => [part.type, part.value]))
  const hour = Number(parts.hour)
  const day = parts.weekday
  if (day === 'Sat') return false
  if (day === 'Sun') return hour >= 18
  if (day === 'Fri') return hour < 17
  return hour !== 17
}
