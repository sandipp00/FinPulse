import { describe, expect, it } from 'vitest'
import { filterNews, formatEventDate, formatEventTime, groupByDate, safeHref } from './news'

const ITEMS = [
  { id: 'a', source: 'coindesk', topics: ['crypto'], instruments: ['BTC/USDT', 'ETH/USDT'] },
  { id: 'b', source: 'fed', topics: ['macro', 'rates'], instruments: [] },
  { id: 'c', source: 'sec', topics: ['equities', 'filings'], instruments: ['AAPL'] },
]

describe('filterNews', () => {
  it('returns everything without filters', () => {
    expect(filterNews(ITEMS)).toHaveLength(3)
  })

  it('combines topic, instrument and source filters', () => {
    expect(filterNews(ITEMS, { topic: 'rates' }).map((i) => i.id)).toEqual(['b'])
    expect(filterNews(ITEMS, { instrument: 'ETH/USDT' }).map((i) => i.id)).toEqual(['a'])
    expect(filterNews(ITEMS, { source: 'sec', topic: 'filings' }).map((i) => i.id)).toEqual(['c'])
    expect(filterNews(ITEMS, { source: 'sec', topic: 'crypto' })).toEqual([])
  })
})

describe('safeHref', () => {
  it('allows only absolute http(s) links', () => {
    expect(safeHref('https://www.bea.gov/news/x')).toBe('https://www.bea.gov/news/x')
    expect(safeHref('http://example.com')).toBe('http://example.com')
    expect(safeHref('javascript:alert(1)')).toBeNull()
    expect(safeHref('/relative')).toBeNull()
    expect(safeHref(undefined)).toBeNull()
  })
})

describe('calendar helpers', () => {
  it('groups events by date in order', () => {
    const groups = groupByDate([
      { date: '2026-11-10', title: 'CPI' },
      { date: '2026-11-06', title: 'Jobs' },
      { date: '2026-11-10', title: 'Other' },
    ])
    expect(groups.map(([d, e]) => [d, e.length])).toEqual([['2026-11-06', 1], ['2026-11-10', 2]])
  })

  it('formats dates with the weekday, and times only when published', () => {
    expect(formatEventDate('2026-11-25')).toBe('Wed, 25 Nov 2026')
    expect(formatEventTime('2026-11-25T13:30:00Z')).toBe('13:30 UTC')
    expect(formatEventTime(null)).toBeNull()
    expect(formatEventTime('garbage')).toBeNull()
  })
})
