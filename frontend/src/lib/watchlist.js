// The right-panel watchlist: the default list, or the user's own symbols in their order.
import { CLASS_LABEL } from './asset'
import { getAssetDetails } from './format'

export const MAX_ITEMS = 60

/** The list with item `index` moved one place up (-1) or down (+1). */
export function move(list, index, step) {
  const target = index + step
  if (target < 0 || target >= list.length) return list
  const next = [...list]
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}

/** The list with `symbol` added at the end, unless it is there already or the list is full. */
export function add(list, symbol) {
  if (!symbol || list.includes(symbol) || list.length >= MAX_ITEMS) return list
  return [...list, symbol]
}

export function remove(list, symbol) {
  return list.filter((s) => s !== symbol)
}

/**
 * Watchlist rows for `symbols`: the default row when there is one (it carries the
 * stored price and metrics), otherwise a row built from the instrument catalogue.
 * Symbols the terminal no longer knows are dropped.
 */
export function resolve(symbols, defaults, instruments) {
  const byDefault = Object.fromEntries(defaults.map((asset) => [asset.symbol, asset]))
  const byInstrument = Object.fromEntries(instruments.map((item) => [item.symbol, item]))
  return symbols.flatMap((symbol) => {
    if (byDefault[symbol]) return [byDefault[symbol]]
    const instrument = byInstrument[symbol]
    if (!instrument) return []
    const details = getAssetDetails(symbol)
    return [{ symbol, name: details.name, color: details.color, type: CLASS_LABEL[instrument.asset_class] ?? 'Asset', price: '—', stored: false }]
  })
}
