// Pure helpers for the asset analysis views. Figures arrive as fractions.

/** {date, value} fractions -> chart points in percent; missing values become gaps. */
export function toPercentPoints(series) {
  return (series ?? []).map((row) => (row.value == null ? { time: row.date } : { time: row.date, value: row.value * 100 }))
}

/** Scoreboard rows sorted by a column; rows without a value (or with an error) go last either way. */
export function sortRows(rows, key, direction = 'desc') {
  const value = (row) => (key === 'name' ? row.asset.name : row[key])
  return [...rows].sort((a, b) => {
    const va = value(a)
    const vb = value(b)
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    const order = typeof va === 'string' ? va.localeCompare(vb) : va - vb
    return direction === 'asc' ? order : -order
  })
}

/** Monthly returns -> one row per year (newest first) with twelve cells and the year's compounded total. */
export function heatmapRows(monthly) {
  const years = new Map()
  for (const { year, month, return: value } of monthly ?? []) {
    if (!years.has(year)) years.set(year, Array(12).fill(null))
    years.get(year)[month - 1] = value
  }
  return [...years.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([year, months]) => {
      const present = months.filter((m) => m != null)
      const total = present.length ? present.reduce((acc, m) => acc * (1 + m), 1) - 1 : null
      return { year, months, total }
    })
}

/** Background for a return cell: green for gains, red for losses, stronger as it grows (capped at 10%). */
export function heatColor(value) {
  if (value == null) return 'transparent'
  const strength = Math.min(Math.abs(value) / 0.1, 1)
  const alpha = (0.12 + strength * 0.55).toFixed(2)
  return value >= 0 ? `rgba(52, 211, 153, ${alpha})` : `rgba(248, 113, 113, ${alpha})`
}

/** An RSI reading in words. */
export function rsiZone(rsi) {
  if (rsi == null) return null
  if (rsi >= 70) return 'overbought'
  if (rsi <= 30) return 'oversold'
  return 'neutral'
}
