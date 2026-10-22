/**
 * Estimated annualized volatility of a portfolio, from the volatility of each holding
 * and the correlations between them (the standard two-asset formula, extended):
 *     sigma_p = sqrt( sum_i sum_j  w_i w_j  sigma_i sigma_j  rho_ij )
 * Cash counts as zero volatility, so it only dilutes the result.
 *
 *   holdings     [{ symbol, weight }]   weight = share of total equity (0..1)
 *   volatility   { symbol: annualized volatility in percent }
 *   correlation  { symbols: [...], matrix: [[...]] }  as returned by /api/risk
 *
 * Returns null when any held asset lacks a volatility or a pairwise correlation.
 */
export function portfolioVolatility(holdings, volatility, correlation) {
  if (holdings.length === 0) return 0

  const index = Object.fromEntries(correlation.symbols.map((symbol, i) => [symbol, i]))
  let variance = 0

  for (const a of holdings) {
    for (const b of holdings) {
      const sigmaA = volatility[a.symbol]
      const sigmaB = volatility[b.symbol]
      if (sigmaA == null || sigmaB == null) return null

      const rho = a.symbol === b.symbol ? 1 : correlation.matrix[index[a.symbol]]?.[index[b.symbol]]
      if (rho == null) return null

      variance += a.weight * b.weight * sigmaA * sigmaB * rho
    }
  }
  return Math.sqrt(Math.max(variance, 0))
}

/** Mean of the off-diagonal correlations (each pair once). Null if there are none. */
export function averageCorrelation(correlation) {
  const { matrix } = correlation
  let sum = 0
  let count = 0
  for (let i = 0; i < matrix.length; i++) {
    for (let j = i + 1; j < matrix.length; j++) {
      if (matrix[i][j] != null) {
        sum += matrix[i][j]
        count += 1
      }
    }
  }
  return count ? sum / count : null
}

/** The least-correlated pair, i.e. the best diversifier. Null if there are none. */
export function mostDiversifyingPair(correlation) {
  const { symbols, matrix } = correlation
  let best = null
  for (let i = 0; i < matrix.length; i++) {
    for (let j = i + 1; j < matrix.length; j++) {
      const value = matrix[i][j]
      if (value != null && (best === null || value < best.value)) {
        best = { a: symbols[i], b: symbols[j], value }
      }
    }
  }
  return best
}

/** 1-based rank of `symbol` when assets are ordered by `field`, highest first. */
export function rankBy(assets, symbol, field) {
  const ordered = assets
    .filter((asset) => asset[field] != null)
    .sort((x, y) => y[field] - x[field])
  const position = ordered.findIndex((asset) => asset.symbol === symbol)
  return position === -1 ? null : { rank: position + 1, of: ordered.length }
}
