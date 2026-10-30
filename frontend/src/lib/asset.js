// Pure helpers for the asset terminal page.

import { ROUTES } from './routes'

export const CLASS_LABEL = { crypto: 'Crypto', stock: 'Stock', index: 'Index', commodity: 'Commodity', fx: 'FX' }
export const CLASS_ORDER = ['crypto', 'stock', 'index', 'commodity', 'fx']

/** The asset a symbol belongs to ("GC=F" and "XAU/USDT" are both gold), or an id itself. */
export function findAsset(assets, key) {
  if (!key) return null
  const lower = key.toLowerCase()
  return assets.find((asset) => asset.id === lower)
    ?? assets.find((asset) => [asset.live, asset.stored, asset.eia, asset.ecb].includes(key))
    ?? null
}

/** Link to an asset's page, by id or by any of its symbols. */
export function assetHref(key) {
  return `${ROUTES.asset}?asset=${encodeURIComponent(key)}`
}

/**
 * Which instrument to chart: the live symbol when it has exchange history (crypto,
 * gold, silver, oil), otherwise the stored daily history. FX has neither: its
 * chart is the ECB reference series. Returns null when there is nothing to chart.
 */
export function chartInstrument(asset, instruments) {
  if (!asset) return null
  const bySymbol = new Map(instruments.map((item) => [item.symbol, item]))
  return bySymbol.get(asset.live) ?? bySymbol.get(asset.stored) ?? null
}

/** Assets grouped by class, in a fixed order, for the picker. */
export function groupAssets(assets) {
  return CLASS_ORDER
    .map((assetClass) => ({ assetClass, label: CLASS_LABEL[assetClass], assets: assets.filter((a) => a.asset_class === assetClass) }))
    .filter((group) => group.assets.length > 0)
}
