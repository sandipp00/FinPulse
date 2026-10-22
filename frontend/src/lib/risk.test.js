import { describe, expect, it } from 'vitest'
import { averageCorrelation, mostDiversifyingPair, portfolioVolatility, rankBy } from './risk'

const correlation = {
  symbols: ['A', 'B', 'C'],
  matrix: [
    [1, 0.5, -0.2],
    [0.5, 1, null],
    [-0.2, null, 1],
  ],
}
const volatility = { A: 40, B: 20, C: 10 }

describe('portfolioVolatility', () => {
  it('equals the asset volatility, scaled by its weight, for a single holding', () => {
    expect(portfolioVolatility([{ symbol: 'A', weight: 0.5 }], volatility, correlation)).toBeCloseTo(20)
  })

  it('applies the two-asset formula', () => {
    const result = portfolioVolatility(
      [{ symbol: 'A', weight: 0.5 }, { symbol: 'B', weight: 0.3 }], volatility, correlation,
    )
    const expected = Math.sqrt(0.5 ** 2 * 40 ** 2 + 0.3 ** 2 * 20 ** 2 + 2 * 0.5 * 0.3 * 40 * 20 * 0.5)
    expect(result).toBeCloseTo(expected, 10)
  })

  it('shows diversification: perfectly correlated is the weighted sum, lower correlation is less', () => {
    const together = { symbols: ['A', 'B'], matrix: [[1, 1], [1, 1]] }
    const apart = { symbols: ['A', 'B'], matrix: [[1, 0], [0, 1]] }
    const holdings = [{ symbol: 'A', weight: 0.5 }, { symbol: 'B', weight: 0.5 }]

    expect(portfolioVolatility(holdings, volatility, together)).toBeCloseTo(0.5 * 40 + 0.5 * 20)
    expect(portfolioVolatility(holdings, volatility, apart)).toBeLessThan(30)
  })

  it('is zero for an all-cash portfolio and null when data is missing', () => {
    expect(portfolioVolatility([], volatility, correlation)).toBe(0)
    expect(portfolioVolatility([{ symbol: 'B', weight: 0.2 }, { symbol: 'C', weight: 0.2 }], volatility, correlation)).toBeNull()
    expect(portfolioVolatility([{ symbol: 'Z', weight: 1 }], volatility, correlation)).toBeNull()
  })
})

describe('correlation summaries', () => {
  it('averages each pair once and ignores missing pairs', () => {
    expect(averageCorrelation(correlation)).toBeCloseTo((0.5 + -0.2) / 2)
    expect(averageCorrelation({ symbols: ['A'], matrix: [[1]] })).toBeNull()
  })

  it('finds the best diversifying pair', () => {
    expect(mostDiversifyingPair(correlation)).toEqual({ a: 'A', b: 'C', value: -0.2 })
    expect(mostDiversifyingPair({ symbols: ['A'], matrix: [[1]] })).toBeNull()
  })
})

describe('rankBy', () => {
  const assets = [
    { symbol: 'A', vol: 10 }, { symbol: 'B', vol: 30 }, { symbol: 'C', vol: 20 }, { symbol: 'D', vol: null },
  ]

  it('ranks highest first and skips assets without the field', () => {
    expect(rankBy(assets, 'B', 'vol')).toEqual({ rank: 1, of: 3 })
    expect(rankBy(assets, 'A', 'vol')).toEqual({ rank: 3, of: 3 })
    expect(rankBy(assets, 'D', 'vol')).toBeNull()
    expect(rankBy(assets, 'Z', 'vol')).toBeNull()
  })

  it('does not reorder the input', () => {
    rankBy(assets, 'A', 'vol')
    expect(assets.map((a) => a.symbol)).toEqual(['A', 'B', 'C', 'D'])
  })
})
