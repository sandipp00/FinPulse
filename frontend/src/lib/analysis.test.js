import { describe, expect, it } from 'vitest'
import { heatColor, heatmapRows, rsiZone, sortRows, toPercentPoints } from './analysis'

describe('analysis helpers', () => {
  it('turns fractions into percent chart points, keeping gaps', () => {
    expect(toPercentPoints([{ date: '2026-01-02', value: -0.125 }, { date: '2026-01-03', value: null }]))
      .toEqual([{ time: '2026-01-02', value: -12.5 }, { time: '2026-01-03' }])
  })

  it('sorts rows by a column, missing values last', () => {
    const rows = [
      { asset: { name: 'B' }, return_1y: 0.1 },
      { asset: { name: 'A' }, return_1y: null },
      { asset: { name: 'C' }, return_1y: 0.3 },
    ]
    expect(sortRows(rows, 'return_1y').map((r) => r.asset.name)).toEqual(['C', 'B', 'A'])
    expect(sortRows(rows, 'return_1y', 'asc').map((r) => r.asset.name)).toEqual(['B', 'C', 'A'])
    expect(sortRows(rows, 'name', 'asc').map((r) => r.asset.name)).toEqual(['A', 'B', 'C'])
  })

  it('builds yearly heatmap rows, newest first, with compounded totals', () => {
    const rows = heatmapRows([
      { year: 2025, month: 11, return: 0.1 },
      { year: 2025, month: 12, return: -0.1 },
      { year: 2026, month: 1, return: 0.05 },
    ])
    expect(rows.map((r) => r.year)).toEqual([2026, 2025])
    expect(rows[1].months[10]).toBe(0.1)
    expect(rows[1].months[0]).toBeNull()
    expect(rows[1].total).toBeCloseTo(1.1 * 0.9 - 1)
  })

  it('colours gains and losses and names RSI zones', () => {
    expect(heatColor(0.05)).toMatch(/^rgba\(52, 211, 153/)
    expect(heatColor(-0.05)).toMatch(/^rgba\(248, 113, 113/)
    expect(heatColor(null)).toBe('transparent')
    expect([rsiZone(75), rsiZone(25), rsiZone(50), rsiZone(null)]).toEqual(['overbought', 'oversold', 'neutral', null])
  })
})
