// Earnings dates and results (backend/earnings.py) in plain words.

export const TIMING_LABEL = { before_open: 'Before open', after_close: 'After close' }
export const CERTAINTY_LABEL = { expected: 'Expected', estimated: 'Estimated' }

const dayFormat = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' })

/** "Mon 2 Nov" from "2026-11-02". */
export function formatDay(iso) {
  return iso ? dayFormat.format(new Date(`${iso}T00:00:00Z`)) : '—'
}

/** "$2.49" or "—"; EPS can be negative. */
export function formatEps(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  return `${number < 0 ? '-' : ''}$${Math.abs(number).toFixed(2)}`
}

/** Days from `today` (YYYY-MM-DD) to `iso`. */
export function daysUntil(iso, today) {
  return Math.round((Date.parse(`${iso}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000)
}

/** Upcoming reports within `days` of `today`. */
export function reportsWithin(upcoming, today, days) {
  return (upcoming ?? []).filter((r) => {
    const d = daysUntil(r.date, today)
    return d >= 0 && d <= days
  })
}

/** Reports grouped by date, in order: [[date, reports], ...]. */
export function byDate(upcoming) {
  const groups = new Map()
  for (const report of upcoming ?? []) {
    if (!groups.has(report.date)) groups.set(report.date, [])
    groups.get(report.date).push(report)
  }
  return [...groups]
}

/** How the consensus compares with the same quarter a year earlier, e.g. "+101% on a year ago". */
export function growthVsLastYear(report) {
  const { eps_forecast: forecast, eps_last_year: last } = report
  if (forecast == null || last == null || last <= 0) return null
  const pct = (forecast / last - 1) * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}% on a year ago`
}

/** Today's date (UTC) as YYYY-MM-DD. */
export function todayIso(now = new Date()) {
  return now.toISOString().slice(0, 10)
}
