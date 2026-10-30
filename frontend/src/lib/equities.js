// The Equities page: the followed stocks (from /api/asset-registry), largest first, by sector.

/**
 * Stocks from the asset registry as watchlist rows, in registry order (largest market
 * cap first). A stock with stored history keeps its stored row (latest close, daily change).
 */
export function equityRows(registry, storedAssets = []) {
  const stored = Object.fromEntries(storedAssets.map((asset) => [asset.symbol, asset]))
  return registry
    .filter((asset) => asset.asset_class === 'stock' && asset.live)
    .map((asset) => ({
      price: '—',
      change: '—',
      positive: true,
      ...stored[asset.live],
      symbol: asset.live,
      name: asset.name,
      sector: asset.sector,
      type: 'Stock',
    }))
}

/** Sectors present in the rows, in first-seen order, with how many stocks each has. */
export function sectorCounts(rows) {
  const counts = new Map()
  for (const row of rows) {
    if (row.sector) counts.set(row.sector, (counts.get(row.sector) ?? 0) + 1)
  }
  return [...counts].map(([sector, count]) => ({ sector, count }))
}
