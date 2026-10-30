import { describe, expect, it } from 'vitest'
import { curvePoints, shapeReading } from './vixCurve'

const curve = [
  { symbol: '^VIX9D', value: 20 }, { symbol: '^VIX', value: 22 }, { symbol: '^VIX3M', value: 24 },
  { symbol: '^VIX6M', value: null }, { symbol: '^VIX1Y', value: 21 },
]

describe('curvePoints', () => {
  it('spaces horizons evenly, puts higher values higher, keeps missing ones without a y', () => {
    const points = curvePoints(curve, 420, 150)
    expect(points.map((p) => Math.round(p.x))).toEqual([26, 118, 210, 302, 394])
    expect(points[2].y).toBeLessThan(points[1].y)  // 24 is above 22
    expect(points[0].y).toBe(144)                   // the lowest value sits at the bottom
    expect(points[3].y).toBeNull()
  })

  it('copes with no values at all', () => {
    expect(curvePoints([{ symbol: 'A', value: null }], 100, 50)[0].y).toBeNull()
  })
})

describe('shapeReading', () => {
  it('reads each shape', () => {
    expect(shapeReading('contango')).toMatch(/usual calm/)
    expect(shapeReading('backwardation')).toMatch(/sell-offs/)
    expect(shapeReading('flat')).toMatch(/about the same/)
    expect(shapeReading(null)).toMatch(/not available/)
  })
})
