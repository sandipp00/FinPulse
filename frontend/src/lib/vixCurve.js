// The VIX term structure (backend/vix_curve.py): drawing positions and plain words.

const PAD = 26

/**
 * Screen positions for the curve: horizons evenly spaced left to right, values scaled
 * to the height with some headroom. A point with no value keeps its x and has y null.
 */
export function curvePoints(curve, width, height) {
  const values = curve.map((p) => p.value).filter((v) => v != null)
  if (values.length === 0) return curve.map((p, i) => ({ ...p, x: PAD + i * ((width - 2 * PAD) / Math.max(curve.length - 1, 1)), y: null }))
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const top = 20
  const bottom = height - 6
  return curve.map((p, i) => ({
    ...p,
    x: PAD + i * ((width - 2 * PAD) / Math.max(curve.length - 1, 1)),
    y: p.value == null ? null : bottom - ((p.value - lo) / span) * (bottom - top),
  }))
}

export function shapeReading(shape) {
  if (shape === 'contango') return 'contango: longer horizons priced higher, the usual calm state.'
  if (shape === 'backwardation') return 'backwardation: near-term fear above longer-term, as in sell-offs.'
  if (shape === 'flat') return 'flat: near-term and longer-term volatility priced about the same.'
  return 'not available.'
}
