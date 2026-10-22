import { describe, expect, it, vi } from 'vitest'
import { STORAGE_KEY, createNotificationStore } from './notificationStore'

function fakeStorage(initial) {
  const data = new Map(initial === undefined ? [] : [[STORAGE_KEY, initial]])
  return {
    data,
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
  }
}

const context = (price = 80_000) => ({ ticks: { 'BTC/USDT': { price } }, liveSymbols: ['BTC/USDT'] })
const saved = (storage) => JSON.parse(storage.data.get(STORAGE_KEY))
const clock = () => ({ now: () => 1_700_000_000_000 })

describe('alerts', () => {
  it('adds a valid alert, saves it, and reports validation errors without changing anything', () => {
    const storage = fakeStorage()
    const store = createNotificationStore(storage, clock())

    const bad = store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 70_000 }, context())
    expect(bad.ok).toBe(false)
    expect(store.getState().alerts).toEqual([])
    expect(storage.data.size).toBe(0)                          // nothing written for a refused alert

    const good = store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 82_000 }, context())
    expect(good.ok).toBe(true)
    expect(store.getState().alerts).toHaveLength(1)
    expect(saved(storage).alerts[0]).toMatchObject({ symbol: 'BTC/USDT', direction: 'above', price: 82_000 })
  })

  it('removes an alert by id', () => {
    const store = createNotificationStore(fakeStorage(), clock())
    store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 82_000 }, context())

    store.removeAlert(store.getState().alerts[0].id)

    expect(store.getState().alerts).toEqual([])
  })

  it('fires when the price reaches it: notification, toast, alert consumed, all saved', () => {
    const storage = fakeStorage()
    const store = createNotificationStore(storage, clock())
    store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 82_000 }, context())

    store.ingestTicks({ 'BTC/USDT': { price: 81_999 } })
    expect(store.getState().notifications).toEqual([])        // not yet

    store.ingestTicks({ 'BTC/USDT': { price: 82_050 } })

    const state = store.getState()
    expect(state.alerts).toEqual([])                          // an alert fires once
    expect(state.notifications).toHaveLength(1)
    expect(state.notifications[0]).toMatchObject({ kind: 'alert', read: false, ts: 1_700_000_000_000 })
    expect(state.toasts.map((t) => t.id)).toEqual([state.notifications[0].id])
    expect(saved(storage).notifications).toHaveLength(1)
    expect(saved(storage).toasts).toBeUndefined()             // toasts are momentary, never saved

    store.ingestTicks({ 'BTC/USDT': { price: 90_000 } })       // and does not fire again
    expect(store.getState().notifications).toHaveLength(1)
  })

  it('keeps the same state object when nothing changes (so React does not re-render)', () => {
    const store = createNotificationStore(fakeStorage(), clock())
    const before = store.getState()

    store.ingestTicks({ 'BTC/USDT': { price: 1 } })           // no alerts
    store.markAllRead()                                       // nothing unread
    store.removeAlert('nope')
    store.dismissToast('nope')
    store.clearNotifications()

    expect(store.getState()).toBe(before)
  })
})

describe('rating changes', () => {
  it('first sight is silent, a later change notifies once', () => {
    const storage = fakeStorage()
    const store = createNotificationStore(storage, clock())

    store.ingestSignals([{ symbol: 'BTC/USDT', rating: 'Hold', score: 5 }])
    expect(store.getState().notifications).toEqual([])
    expect(saved(storage).ratings).toEqual({ 'BTC/USDT': 'Hold' })

    store.ingestSignals([{ symbol: 'BTC/USDT', rating: 'Buy', score: 30 }])
    expect(store.getState().notifications).toHaveLength(1)
    expect(store.getState().notifications[0]).toMatchObject({ kind: 'signal', text: "Bitcoin's daily signal changed from Hold to Buy." })

    const after = store.getState()
    store.ingestSignals([{ symbol: 'BTC/USDT', rating: 'Buy', score: 31 }])   // unchanged
    expect(store.getState()).toBe(after)
  })

  it('remembers ratings across a reload, so a change while the page was closed is noticed', () => {
    const storage = fakeStorage()
    createNotificationStore(storage, clock()).ingestSignals([{ symbol: 'BTC/USDT', rating: 'Hold', score: 5 }])

    const reopened = createNotificationStore(storage, clock())
    reopened.ingestSignals([{ symbol: 'BTC/USDT', rating: 'Sell', score: -30 }])

    expect(reopened.getState().notifications[0].text).toContain('from Hold to Sell')
  })
})

describe('reading, clearing and toasts', () => {
  function withTwoNotes() {
    const store = createNotificationStore(fakeStorage(), clock())
    store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 81_000 }, context())
    store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 82_000 }, context())
    store.ingestTicks({ 'BTC/USDT': { price: 83_000 } })
    return store
  }

  it('marks everything read, dismisses a toast and clears the list', () => {
    const store = withTwoNotes()
    expect(store.getState().notifications.filter((n) => !n.read)).toHaveLength(2)

    store.markAllRead()
    expect(store.getState().notifications.every((n) => n.read)).toBe(true)

    store.dismissToast(store.getState().toasts[0].id)
    expect(store.getState().toasts).toHaveLength(1)

    store.clearNotifications()
    expect(store.getState()).toMatchObject({ notifications: [], toasts: [] })
  })

  it('shows at most three toasts at a time', () => {
    const store = createNotificationStore(fakeStorage(), clock())
    for (let i = 0; i < 5; i++) store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 81_000 + i }, context())

    store.ingestTicks({ 'BTC/USDT': { price: 90_000 } })

    expect(store.getState().notifications).toHaveLength(5)
    expect(store.getState().toasts).toHaveLength(3)
  })

  it('tells subscribers about changes, and stops after they unsubscribe', () => {
    const store = createNotificationStore(fakeStorage(), clock())
    const listener = vi.fn()
    const unsubscribe = store.subscribe(listener)

    store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 82_000 }, context())
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 83_000 }, context())
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('persistence is defensive', () => {
  it('starts empty from missing, corrupt or wrongly shaped saved data', () => {
    for (const raw of [undefined, 'not json', '[]', '42', 'null', '{"alerts": "nope", "notifications": 7, "ratings": []}']) {
      const state = createNotificationStore(fakeStorage(raw), clock()).getState()
      expect(state).toMatchObject({ alerts: [], notifications: [], ratings: {}, toasts: [] })
    }
  })

  it('keeps the good entries and drops malformed ones', () => {
    const raw = JSON.stringify({
      alerts: [
        { id: 'a1', symbol: 'BTC/USDT', direction: 'above', price: 90_000 },
        { id: 'bad', symbol: 'BTC/USDT', direction: 'sideways', price: 1 },
        null,
      ],
      notifications: [
        { id: 'n1', text: 'hi', ts: 5, read: false },
        { id: 'n2', text: 'no timestamp', read: false },
      ],
      ratings: { 'BTC/USDT': 'Buy', 'ETH/USDT': 7 },
    })

    const state = createNotificationStore(fakeStorage(raw), clock()).getState()

    expect(state.alerts.map((a) => a.id)).toEqual(['a1'])
    expect(state.notifications.map((n) => n.id)).toEqual(['n1'])
    expect(state.ratings).toEqual({ 'BTC/USDT': 'Buy' })
  })

  it('keeps working when storage is missing or throws', () => {
    for (const storage of [null, undefined, {
      getItem() { throw new Error('blocked') },
      setItem() { throw new Error('quota exceeded') },
    }]) {
      const store = createNotificationStore(storage, clock())
      const result = store.addAlert({ symbol: 'BTC/USDT', direction: 'above', price: 82_000 }, context())

      expect(result.ok).toBe(true)
      expect(store.getState().alerts).toHaveLength(1)
    }
  })
})
