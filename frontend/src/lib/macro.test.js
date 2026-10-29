import { describe, expect, it } from 'vitest'
import { formatMacroChange, formatMacroValue, formatObservationDate, toChartPoints, withinYears } from './macro'

describe('formatMacroValue', () => {
  it('shows percentage series with a percent sign', () => {
    expect(formatMacroValue(4.3, '%')).toBe('4.30%')
    expect(formatMacroValue(4.3, '% Chg.')).toBe('4.30%')
  })

  it('shows other units as plain or compact numbers', () => {
    expect(formatMacroValue(321.465, 'Index 1982-1984=100')).toBe('321.47')
    expect(formatMacroValue(159_123, 'Thous. of Persons')).toBe('159,123')
    expect(formatMacroValue(23_456_789, 'Bil. of Chn. 2017 $')).toBe('23.46M')
  })

  it('shows a dash when there is no value', () => {
    expect(formatMacroValue(null, '%')).toBe('—')
    expect(formatMacroValue(undefined)).toBe('—')
  })
})

describe('formatMacroChange', () => {
  it('reports percentage series in percentage points', () => {
    expect(formatMacroChange(0.2, '%')).toBe('+0.20 pts')
    expect(formatMacroChange(-0.25, '%')).toBe('-0.25 pts')
  })

  it('signs other changes', () => {
    expect(formatMacroChange(142, 'Thous. of Persons')).toBe('+142')
    expect(formatMacroChange(-3.5, 'Index')).toBe('-3.5')
    expect(formatMacroChange(0, 'Index')).toBe('0')
    expect(formatMacroChange(null, '%')).toBe('—')
  })
})

describe('withinYears', () => {
  const rows = [
    { date: '2016-10-01', value: 1 },
    { date: '2021-09-30', value: 2 },
    { date: '2021-10-01', value: 3 },
    { date: '2026-10-01', value: 4 },
  ]

  it('keeps observations within N years of the newest', () => {
    expect(withinYears(rows, 5).map((r) => r.date)).toEqual(['2021-10-01', '2026-10-01'])
    expect(withinYears(rows, 10)).toHaveLength(4)
  })

  it('keeps everything without a limit, and handles no data', () => {
    expect(withinYears(rows, null)).toHaveLength(4)
    expect(withinYears([], 1)).toEqual([])
  })
})

describe('toChartPoints', () => {
  it('turns missing values into gaps rather than zeros', () => {
    expect(toChartPoints([
      { date: '2026-07-01', value: 4.1 },
      { date: '2026-08-01', value: null },
    ])).toEqual([{ time: '2026-07-01', value: 4.1 }, { time: '2026-08-01' }])
  })
})

describe('formatObservationDate', () => {
  it('names the period the way the series is published', () => {
    expect(formatObservationDate('2026-09-01', 'Monthly')).toBe('Sep 2026')
    expect(formatObservationDate('2026-07-01', 'Quarterly')).toBe('Q3 2026')
    expect(formatObservationDate('2026-10-28', 'Daily')).toBe('28 Oct 2026')
    expect(formatObservationDate(null, 'Daily')).toBe('—')
  })
})
