import { useEffect, useSyncExternalStore } from 'react'
import { getSignals } from '../api/finpulse'
import { createNotificationStore } from '../lib/notificationStore'
import { unreadCount } from '../lib/notifications'

// One store for the whole page. localStorage can throw or be missing (private mode, blocked
// cookies), in which case the store simply works without saving.
function browserStorage() {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export const notificationStore = createNotificationStore(browserStorage())

// Daily ratings only change when a daily candle closes, so a slow poll is plenty.
const SIGNAL_POLL_MS = 5 * 60_000

/** The notification centre: state plus the actions that change it. */
export function useNotifications() {
  const state = useSyncExternalStore(notificationStore.subscribe, notificationStore.getState)
  return {
    alerts: state.alerts,
    notifications: state.notifications,
    toasts: state.toasts,
    unread: unreadCount(state.notifications),
    addAlert: notificationStore.addAlert,
    removeAlert: notificationStore.removeAlert,
    markAllRead: notificationStore.markAllRead,
    clearNotifications: notificationStore.clearNotifications,
    dismissToast: notificationStore.dismissToast,
  }
}

/**
 * Feed the store: every price tick is checked against the alerts, and the daily
 * ratings are polled so a change can be announced. Mount this once, high in the app.
 */
export function useNotificationFeeds(ticks) {
  useEffect(() => {
    notificationStore.ingestTicks(ticks)
  }, [ticks])

  useEffect(() => {
    let cancelled = false

    const poll = () => {
      getSignals('1d')
        .then((response) => {
          if (!cancelled) notificationStore.ingestSignals(response.signals ?? [])
        })
        .catch(() => {
          // A failed poll just means no news this time; the next one tries again.
        })
    }

    poll()
    const timer = setInterval(poll, SIGNAL_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])
}
