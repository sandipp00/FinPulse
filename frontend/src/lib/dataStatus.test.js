import { describe, expect, it } from 'vitest'
import {
  STALE_AFTER_MS,
  ageInDays,
  apiState,
  describeSource,
  formatAge,
  formatAsOfDate,
  isCachedFallback,
  latestStoredTimestamp,
  weekdaysSince,
  parseTimestamp,
  storedStatus,
  tickStatus,
} from './dataStatus'

const NOW = Date.UTC(2026, 9, 29, 12, 0, 0)

describe('tickStatus', () => {
  const tick = { symbol: 'BTC/USDT', price: 83000, seenAt: NOW - 1000 }

  it('is live for a recent tick while the feed is connected', () => {
    expect(tickStatus(tick, 'live', NOW)).toBe('live')
  })

  it('is stale once the last tick is older than the threshold', () => {
    expect(tickStatus({ ...tick, seenAt: NOW - STALE_AFTER_MS - 1 }, 'live', NOW)).toBe('stale')
    expect(tickStatus({ ...tick, seenAt: NOW - STALE_AFTER_MS }, 'live', NOW)).toBe('live')
  })

  it('is stale whenever the feed is not connected, however recent the tick', () => {
    for (const status of ['connecting', 'reconnecting', 'offline']) {
      expect(tickStatus(tick, status, NOW)).toBe('stale')
    }
  })

  it('is stale when the receive time is unknown', () => {
    expect(tickStatus({ symbol: 'BTC/USDT', price: 1 }, 'live', NOW)).toBe('stale')
  })

  it('is unavailable without a usable price', () => {
    expect(tickStatus(undefined, 'live', NOW)).toBe('unavailable')
    expect(tickStatus({ ...tick, price: null }, 'live', NOW)).toBe('unavailable')
    expect(tickStatus({ ...tick, price: 'abc' }, 'live', NOW)).toBe('unavailable')
  })
})

describe('storedStatus', () => {
  it('calls a stored close historical, never live', () => {
    expect(storedStatus({ latest_price: 230.1, latest_timestamp: '2026-10-14 00:00:00+00:00' })).toBe('historical')
  })

  it('is unavailable without a price', () => {
    expect(storedStatus(undefined)).toBe('unavailable')
    expect(storedStatus({ latest_price: null })).toBe('unavailable')
  })
})

describe('timestamps', () => {
  it('parses the formats the API returns', () => {
    expect(parseTimestamp('2026-10-14 00:00:00+00:00')?.toISOString()).toBe('2026-10-14T00:00:00.000Z')
    expect(parseTimestamp('2026-10-14T00:00:00Z')?.toISOString()).toBe('2026-10-14T00:00:00.000Z')
    expect(parseTimestamp(NOW)?.getTime()).toBe(NOW)
    expect(parseTimestamp(new Date(NOW))?.getTime()).toBe(NOW)
    expect(parseTimestamp('')).toBeNull()
    expect(parseTimestamp(null)).toBeNull()
    expect(parseTimestamp('not a date')).toBeNull()
  })

  it('counts whole days of age', () => {
    expect(ageInDays('2026-10-14 00:00:00+00:00', NOW)).toBe(15)
    expect(ageInDays('2026-10-29 00:00:00+00:00', NOW)).toBe(0)
    expect(ageInDays('2026-11-30 00:00:00+00:00', NOW)).toBe(0)
    expect(ageInDays(new Date('2026-10-14T00:00:00Z'), NOW)).toBe(15)
    expect(ageInDays(null, NOW)).toBeNull()
  })

  it('formats an as-of date in UTC', () => {
    expect(formatAsOfDate('2026-10-14 00:00:00+00:00')).toBe('14 Oct')
    expect(formatAsOfDate('2026-10-14 00:00:00+00:00', { withYear: true })).toBe('14 Oct 2026')
    expect(formatAsOfDate(new Date('2026-10-14T00:00:00Z'), { withYear: true })).toBe('14 Oct 2026')
    expect(formatAsOfDate(undefined)).toBe('—')
  })

  it('formats an age', () => {
    expect(formatAge(2400)).toBe('2s ago')
    expect(formatAge(5 * 60_000)).toBe('5m ago')
    expect(formatAge(3 * 3_600_000)).toBe('3h ago')
    expect(formatAge(15 * 86_400_000)).toBe('15d ago')
    expect(formatAge(-50)).toBe('0s ago')
    expect(formatAge(null)).toBe('—')
  })

  it('finds where the stored history ends', () => {
    const assets = [
      { latest_timestamp: '2026-10-13 00:00:00+00:00' },
      { latest_timestamp: '2026-10-14 00:00:00+00:00' },
      { latest_timestamp: null },
    ]
    expect(latestStoredTimestamp(assets)?.toISOString()).toBe('2026-10-14T00:00:00.000Z')
    expect(latestStoredTimestamp([])).toBeNull()
  })
})

describe('apiState', () => {
  it('is ok only for a healthy answer', () => {
    expect(apiState({ health: { status: 'healthy' }, loading: false })).toBe('ok')
  })

  it('is checking before the first answer', () => {
    expect(apiState({ health: null, loading: true })).toBe('checking')
  })

  it('is an error when the check failed or answered unhealthy', () => {
    expect(apiState({ health: { status: 'healthy' }, healthError: 'Network error', loading: false })).toBe('error')
    expect(apiState({ health: { status: 'degraded' }, loading: false })).toBe('error')
    expect(apiState({ health: null, loading: false })).toBe('error')
  })
})

describe('describeSource', () => {
  const meta = {
    provider: 'binance',
    endpoint: 'api.binance.com',
    status: 'historical',
    retrieved_at: '2026-10-29T17:31:02Z',
    source_timestamp: '2026-10-29T17:00:00Z',
    cache_age_seconds: 0,
    notes: [],
  }

  it('names the provider, host and both timestamps', () => {
    expect(describeSource(meta)).toBe('Binance (api.binance.com) · fetched 17:31:02 UTC · latest bar 17:00:00 UTC')
  })

  it('leaves out what the API did not send', () => {
    expect(describeSource({ provider: 'database', status: 'historical' })).toBe('Local database')
    expect(describeSource({ provider: 'other', endpoint: null, retrieved_at: 'garbage' })).toBe('other')
  })

  it('is null without meta (an older API)', () => {
    expect(describeSource(undefined)).toBeNull()
  })

  it('spots a cached fallback only when the API says so', () => {
    expect(isCachedFallback({ ...meta, status: 'cached' })).toBe(true)
    expect(isCachedFallback(meta)).toBe(false)
    expect(isCachedFallback(null)).toBe(false)
  })
})

describe('weekdaysSince', () => {
  // Thursday 29 Oct 2026, midday UTC.
  const THU = Date.UTC(2026, 9, 29, 12)

  it('counts completed weekdays after the last stored day', () => {
    expect(weekdaysSince('2026-10-28 00:00:00+00:00', THU)).toBe(0) // Wednesday's close is the latest possible
    expect(weekdaysSince('2026-10-27T00:00:00Z', THU)).toBe(1)
    expect(weekdaysSince('2026-10-14T00:00:00Z', THU)).toBe(10)
  })

  it('skips weekends', () => {
    const MON = Date.UTC(2026, 10, 2, 12)
    expect(weekdaysSince('2026-10-30T00:00:00Z', MON)).toBe(0) // Friday's close, seen on Monday
    expect(weekdaysSince('2026-10-29T00:00:00Z', MON)).toBe(1)
  })

  it('is null for an unknown date', () => {
    expect(weekdaysSince(null, THU)).toBeNull()
  })
})
