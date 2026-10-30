// A quick read of a group of assets: how many are up and down, the average move,
// and the biggest gainer and loser. Uses the live change where there is a tick,
// otherwise the last stored daily change.

/** The change used for an asset, in percent, or null. */
export function changeOf(asset, ticks) {
  const tick = ticks[asset.symbol]
  if (tick?.change_pct_24h != null) return Number(tick.change_pct_24h)
  return asset.daily_change_pct != null ? Number(asset.daily_change_pct) : null
}

export function summarize(assets, ticks) {
  const moves = assets
    .map((asset) => ({ symbol: asset.symbol, name: asset.name ?? asset.symbol, change: changeOf(asset, ticks) }))
    .filter((move) => move.change != null && Number.isFinite(move.change))
  const sorted = [...moves].sort((a, b) => b.change - a.change)
  return {
    count: assets.length,
    priced: moves.length,
    up: moves.filter((move) => move.change > 0).length,
    down: moves.filter((move) => move.change < 0).length,
    average: moves.length ? moves.reduce((sum, move) => sum + move.change, 0) / moves.length : null,
    best: sorted[0] ?? null,
    worst: sorted.length > 1 ? sorted.at(-1) : null,
  }
}
