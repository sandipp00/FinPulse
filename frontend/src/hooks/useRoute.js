import { useSyncExternalStore } from 'react'
import { routeFor } from '../lib/routes'

function subscribe(callback) {
  window.addEventListener('popstate', callback)
  return () => window.removeEventListener('popstate', callback)
}

const currentPath = () => window.location.pathname

/**
 * Go to another page of the app without reloading it. With `replace`, the current
 * history entry is swapped instead of a new one being added (so Back skips it).
 */
export function navigate(path, { replace = false } = {}) {
  window.history[replace ? 'replaceState' : 'pushState'](null, '', path)
  window.scrollTo({ top: 0 })
  // pushState does not announce itself, so tell the subscribers ourselves.
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/** The current route name (see lib/routes.js), following the address bar including Back/Forward. */
export function useRoute() {
  return routeFor(useSyncExternalStore(subscribe, currentPath, () => '/'))
}
