// Formatting and charting helpers for FRED macro series (see backend/macro.py).

const isPercent = (unitsShort) => typeof unitsShort === 'string' && unitsShort.includes('%')

const plain = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 })

/** A value in its series' units: "4.30%" for percentages, otherwise a plain number. */
export function formatMacroValue(value, unitsShort) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const number = Number(value)
  if (isPercent(unitsShort)) return `${number.toFixed(2)}%`
  return Math.abs(number) >= 1e6 ? compact.format(number) : plain.format(number)
}

/** A change between two observations; percentage series change in percentage points. */
export function formatMacroChange(change, unitsShort) {
  if (change == null || !Number.isFinite(Number(change))) return '—'
  const number = Number(change)
  const sign = number > 0 ? '+' : ''
  if (isPercent(unitsShort)) return `${sign}${number.toFixed(2)} pts`
  return `${sign}${Math.abs(number) >= 1e6 ? compact.format(number) : plain.format(number)}`
}

/** Observations within `years` of the newest one (all of them for `years` null). */
export function withinYears(observations, years) {
  if (!years || observations.length === 0) return observations
  const last = new Date(`${observations.at(-1).date}T00:00:00Z`)
  const cutoff = new Date(Date.UTC(last.getUTCFullYear() - years, last.getUTCMonth(), last.getUTCDate()))
  const from = cutoff.toISOString().slice(0, 10)
  return observations.filter((row) => row.date >= from)
}

/**
 * Points for a line chart. A missing value becomes a whitespace point (time only),
 * so the line shows a gap there instead of joining across it.
 */
export function toChartPoints(observations) {
  return observations.map((row) => (row.value == null ? { time: row.date } : { time: row.date, value: row.value }))
}

const dateFormat = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
const monthFormat = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' })
const quarter = (date) => `Q${Math.floor(date.getUTCMonth() / 3) + 1} ${date.getUTCFullYear()}`

/** An observation date as the series' frequency names it: "Sep 2026", "Q3 2026" or "28 Oct 2026". */
export function formatObservationDate(isoDate, frequency) {
  if (!isoDate) return '—'
  const date = new Date(`${isoDate}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return '—'
  const kind = (frequency ?? '').toLowerCase()
  if (kind.startsWith('quarterly')) return quarter(date)
  if (kind.startsWith('monthly')) return monthFormat.format(date)
  return dateFormat.format(date)
}

export const CATEGORY_LABEL = {
  inflation: 'Inflation',
  rates: 'Policy rate',
  yields: 'Treasury yields',
  growth: 'Growth',
  employment: 'Employment',
}
