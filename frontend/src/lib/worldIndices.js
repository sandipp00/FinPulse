// Pure helpers for the World indices page.

/** Indices in a region (or all) matching a search on name, country or symbol. */
export function filterIndices(indices, { region = 'all', query = '' } = {}) {
  const q = query.trim().toLowerCase().replace(/^\^/, '')
  return indices.filter((index) => (region === 'all' || index.region === region)
    && (!q || [index.name, index.country, index.symbol].some((text) => text.toLowerCase().replace(/^\^/, '').includes(q))))
}

/** How many of these indices are live now, and their average change since the previous close. */
export function regionSummary(indices, ticks, statuses) {
  const changes = indices.map((index) => ticks[index.symbol]?.change_pct_24h).filter((value) => value != null)
  return {
    count: indices.length,
    live: indices.filter((index) => statuses[index.symbol] === 'live').length,
    open: indices.filter((index) => ['live', 'delayed'].includes(statuses[index.symbol]) && ticks[index.symbol]?.market_open !== false).length,
    averageChange: changes.length ? changes.reduce((sum, value) => sum + value, 0) / changes.length : null,
    up: changes.filter((value) => value > 0).length,
    down: changes.filter((value) => value < 0).length,
  }
}

/** Net change in index points, from the price and previous close. */
export function netChange(tick) {
  if (!tick || tick.price == null || tick.previous_close == null) return null
  return tick.price - tick.previous_close
}
