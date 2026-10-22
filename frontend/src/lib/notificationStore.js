import {
  addNotifications,
  alertNotification,
  detectRatingChanges,
  evaluateAlerts,
  ratingNotification,
  validateAlert,
  MAX_ALERTS,
  MAX_NOTIFICATIONS,
} from './notifications'

export const STORAGE_KEY = 'finpulse:notifications:v1'
const MAX_TOASTS = 3

const EMPTY = { alerts: [], notifications: [], ratings: {} }

const isAlert = (a) => a && typeof a.id === 'string' && typeof a.symbol === 'string'
  && (a.direction === 'above' || a.direction === 'below') && Number.isFinite(a.price)
const isNotification = (n) => n && typeof n.id === 'string' && typeof n.text === 'string'
  && Number.isFinite(n.ts) && typeof n.read === 'boolean'

/** Read saved state, tolerating anything: missing, corrupt, from another version. */
function load(storage) {
  try {
    const data = JSON.parse(storage?.getItem(STORAGE_KEY) ?? 'null')
    if (!data || typeof data !== 'object') return EMPTY

    const ratings = data.ratings && typeof data.ratings === 'object' && !Array.isArray(data.ratings)
      ? Object.fromEntries(Object.entries(data.ratings).filter(([, rating]) => typeof rating === 'string'))
      : {}

    return {
      alerts: (Array.isArray(data.alerts) ? data.alerts : []).filter(isAlert).slice(0, MAX_ALERTS),
      notifications: (Array.isArray(data.notifications) ? data.notifications : []).filter(isNotification).slice(0, MAX_NOTIFICATIONS),
      ratings,
    }
  } catch {
    return EMPTY
  }
}

/**
 * The notification centre's state, kept outside React so price ticks and the signal
 * poll can feed it from anywhere, and persisted to `storage` (the browser's
 * localStorage, or a fake one in tests). React reads it with useSyncExternalStore, so
 * every change must produce a new state object and no-ops must keep the old one.
 */
export function createNotificationStore(storage, { now = () => Date.now() } = {}) {
  let state = { ...load(storage), toasts: [] }
  let lastRaw = readRaw()
  const listeners = new Set()

  function readRaw() {
    try {
      return storage?.getItem(STORAGE_KEY) ?? null
    } catch {
      return null
    }
  }

  /**
   * Other tabs share this storage. Before changing anything, adopt whatever they saved
   * (toasts stay local) so a stale tab never overwrites newer alerts or re-fires one
   * that another tab already consumed. Returns true if the state changed.
   */
  const refresh = () => {
    const raw = readRaw()
    if (raw === lastRaw) return false
    lastRaw = raw
    state = { ...load(storage), toasts: state.toasts }
    return true
  }

  const commit = (next) => {
    state = next
    try {
      const raw = JSON.stringify({
        alerts: state.alerts,
        notifications: state.notifications,
        ratings: state.ratings,
      })
      storage?.setItem(STORAGE_KEY, raw)
      lastRaw = raw
    } catch {
      // Storage may be full or blocked (private mode). The app still works without it.
    }
    listeners.forEach((listener) => listener())
  }

  const withNotifications = (added, extra = {}) => ({
    ...state,
    ...extra,
    notifications: addNotifications(state.notifications, added),
    toasts: [...added, ...state.toasts].slice(0, MAX_TOASTS),
  })

  return {
    getState: () => state,

    /** Called when another tab changes the storage: pick up its changes and re-render. */
    sync() {
      if (refresh()) listeners.forEach((listener) => listener())
    },

    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },

    /** Returns { ok: true } or { ok: false, error } for the form to show. */
    addAlert(input, context) {
      refresh()
      const result = validateAlert(input, { ...context, existing: state.alerts }, now())
      if (result.ok) commit({ ...state, alerts: [...state.alerts, result.alert] })
      return result
    },

    removeAlert(id) {
      refresh()
      if (state.alerts.some((alert) => alert.id === id)) {
        commit({ ...state, alerts: state.alerts.filter((alert) => alert.id !== id) })
      }
    },

    /** Called on every price tick; does nothing unless an alert has been reached. */
    ingestTicks(ticks) {
      if (state.alerts.length === 0) return
      let { remaining, fired } = evaluateAlerts(state.alerts, ticks)
      if (fired.length === 0) return

      // Another tab may have fired these already; look again with its saved state.
      if (refresh()) {
        ;({ remaining, fired } = evaluateAlerts(state.alerts, ticks))
        if (fired.length === 0) {
          listeners.forEach((listener) => listener())
          return
        }
      }

      const stamp = now()
      commit(withNotifications(
        fired.map(({ alert, price }) => alertNotification(alert, price, stamp)),
        { alerts: remaining },
      ))
    },

    /** Called with the latest daily ratings; notifies about any that changed. */
    ingestSignals(signals) {
      refresh()
      const { ratings, changes } = detectRatingChanges(state.ratings, signals)
      const ratingsChanged = JSON.stringify(ratings) !== JSON.stringify(state.ratings)
      if (!ratingsChanged) return

      const stamp = now()
      commit(changes.length
        ? withNotifications(changes.map((change) => ratingNotification(change, stamp)), { ratings })
        : { ...state, ratings })
    },

    markAllRead() {
      refresh()
      if (state.notifications.some((n) => !n.read)) {
        commit({ ...state, notifications: state.notifications.map((n) => (n.read ? n : { ...n, read: true })) })
      }
    },

    clearNotifications() {
      refresh()
      if (state.notifications.length || state.toasts.length) commit({ ...state, notifications: [], toasts: [] })
    },

    dismissToast(id) {
      if (state.toasts.some((toast) => toast.id === id)) {
        commit({ ...state, toasts: state.toasts.filter((toast) => toast.id !== id) })
      }
    },
  }
}
