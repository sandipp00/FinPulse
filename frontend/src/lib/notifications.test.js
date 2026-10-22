import { describe, expect, it } from 'vitest'
import {
  MAX_ALERTS,
  MAX_NOTIFICATIONS,
  addNotifications,
  alertNotification,
  detectRatingChanges,
  evaluateAlerts,
  newId,
  ratingNotification,
  unreadCount,
  validateAlert,
} from './notifications'

const ticks = { 'BTC/USDT': { price: 80_000 }, 'XRP/USDT': { price: 1.32 } }
const context = { ticks, liveSymbols: ['BTC/USDT', 'XRP/USDT'], existing: [] }
const alert = (direction, price, symbol = 'BTC/USDT') => ({ id: `${direction}${price}`, symbol, direction, price })

describe('validateAlert', () => {
  it('accepts an alert on the far side of the current price', () => {
    const above = validateAlert({ symbol: 'BTC/USDT', direction: 'above', price: '82000' }, context, 1000)
    const below = validateAlert({ symbol: 'BTC/USDT', direction: 'below', price: 78_000 }, context, 1000)

    expect(above).toMatchObject({ ok: true, alert: { symbol: 'BTC/USDT', direction: 'above', price: 82_000, createdAt: 1000 } })
    expect(below.ok).toBe(true)
    expect(above.alert.id).toBeTruthy()
  })

  it('refuses an alert that is already true, explaining why', () => {
    const above = validateAlert({ symbol: 'BTC/USDT', direction: 'above', price: 79_000 }, context)
    const below = validateAlert({ symbol: 'BTC/USDT', direction: 'below', price: 81_000 }, context)

    expect(above.ok).toBe(false)
    expect(above.error).toContain('already at $80,000.00')
    expect(above.error).toContain('Choose a higher price')
    expect(below.error).toContain('Choose a lower price')
    expect(validateAlert({ symbol: 'BTC/USDT', direction: 'above', price: 80_000 }, context).ok).toBe(false) // equal counts as reached
  })

  it('rejects bad input', () => {
    const check = (input, text) => expect(validateAlert(input, context)).toEqual({ ok: false, error: expect.stringContaining(text) })

    check({ symbol: 'DOGE/USDT', direction: 'above', price: 1 }, 'live assets')
    check({ symbol: 'BTC/USDT', direction: 'sideways', price: 1 }, 'above or below')
    for (const price of ['', 'abc', 0, -5, NaN, Infinity]) check({ symbol: 'BTC/USDT', direction: 'above', price }, 'greater than zero')
  })

  it('waits for a live price, rejects duplicates and enforces the limit', () => {
    expect(validateAlert({ symbol: 'BTC/USDT', direction: 'above', price: 90_000 }, { ...context, ticks: {} }).error).toContain('waiting for a live price')

    const existing = [alert('above', 90_000)]
    expect(validateAlert({ symbol: 'BTC/USDT', direction: 'above', price: 90_000 }, { ...context, existing }).error).toContain('already have')
    expect(validateAlert({ symbol: 'BTC/USDT', direction: 'above', price: 91_000 }, { ...context, existing }).ok).toBe(true)

    const many = Array.from({ length: MAX_ALERTS }, (_, i) => alert('above', 100_000 + i))
    expect(validateAlert({ symbol: 'BTC/USDT', direction: 'above', price: 200_000 }, { ...context, existing: many }).error).toContain('up to 20')
  })
})

describe('evaluateAlerts', () => {
  it('fires alerts that have been reached, including exactly at the level, and keeps the rest', () => {
    const alerts = [alert('above', 79_000), alert('above', 80_000), alert('above', 81_000), alert('below', 80_500), alert('below', 79_000)]

    const { fired, remaining } = evaluateAlerts(alerts, ticks)

    expect(fired.map(({ alert: a }) => a.id)).toEqual(['above79000', 'above80000', 'below80500'])
    expect(fired[0].price).toBe(80_000)
    expect(remaining.map((a) => a.id)).toEqual(['above81000', 'below79000'])
  })

  it('leaves alerts alone when their asset has no price yet', () => {
    const alerts = [alert('above', 1, 'SOL/USDT')]

    expect(evaluateAlerts(alerts, ticks)).toEqual({ fired: [], remaining: alerts })
  })

  it('does not mutate its input', () => {
    const alerts = [alert('above', 79_000)]
    evaluateAlerts(alerts, ticks)
    expect(alerts).toHaveLength(1)
  })
})

describe('detectRatingChanges', () => {
  const signal = (symbol, rating, score = 10) => ({ symbol, rating, score })

  it('records ratings the first time without announcing them', () => {
    const { ratings, changes } = detectRatingChanges({}, [signal('BTC/USDT', 'Hold')])

    expect(ratings).toEqual({ 'BTC/USDT': 'Hold' })
    expect(changes).toEqual([])
  })

  it('reports a changed rating and ignores an unchanged one', () => {
    const previous = { 'BTC/USDT': 'Hold', 'ETH/USDT': 'Sell' }

    const { ratings, changes } = detectRatingChanges(previous, [signal('BTC/USDT', 'Buy'), signal('ETH/USDT', 'Sell')])

    expect(changes).toEqual([{ symbol: 'BTC/USDT', from: 'Hold', to: 'Buy' }])
    expect(ratings).toEqual({ 'BTC/USDT': 'Buy', 'ETH/USDT': 'Sell' })
    expect(previous['BTC/USDT']).toBe('Hold')           // input untouched
  })

  it('ignores symbols that cannot be rated yet and keeps their last known rating', () => {
    const previous = { 'BTC/USDT': 'Buy' }

    const { ratings, changes } = detectRatingChanges(previous, [{ symbol: 'BTC/USDT', rating: 'Insufficient data', score: null }])

    expect(changes).toEqual([])
    expect(ratings).toEqual(previous)
  })
})

describe('notification builders', () => {
  it('describe an alert in plain words and link to the chart', () => {
    const up = alertNotification(alert('above', 82_000), 82_010.5, 5)
    const down = alertNotification(alert('below', 1.3, 'XRP/USDT'), 1.2987, 5)

    expect(up).toMatchObject({ kind: 'alert', read: false, ts: 5, href: '/markets' })
    expect(up.text).toBe('Bitcoin rose to $82,010.50, reaching your alert at $82,000.00.')
    expect(down.text).toBe('XRP fell to $1.2987, reaching your alert at $1.30.')
  })

  it('describe a rating change and link to the signals', () => {
    const note = ratingNotification({ symbol: 'ETH/USDT', from: 'Hold', to: 'Strong Sell' }, 9)

    expect(note).toMatchObject({ kind: 'signal', href: '/analytics', read: false })
    expect(note.text).toBe("Ethereum's daily signal changed from Hold to Strong Sell.")
  })

  it('get ids that differ and work without crypto.randomUUID', () => {
    const ids = new Set(Array.from({ length: 200 }, newId))
    expect(ids.size).toBe(200)
  })
})

describe('lists', () => {
  it('puts new notifications first and caps the list', () => {
    const old = Array.from({ length: MAX_NOTIFICATIONS }, (_, i) => ({ id: `old${i}`, read: true }))

    const next = addNotifications(old, [{ id: 'new1', read: false }, { id: 'new2', read: false }])

    expect(next).toHaveLength(MAX_NOTIFICATIONS)
    expect(next.slice(0, 2).map((n) => n.id)).toEqual(['new1', 'new2'])
    expect(next.at(-1).id).toBe(`old${MAX_NOTIFICATIONS - 3}`)
  })

  it('counts unread', () => {
    expect(unreadCount([{ read: false }, { read: true }, { read: false }])).toBe(2)
    expect(unreadCount([])).toBe(0)
  })
})
