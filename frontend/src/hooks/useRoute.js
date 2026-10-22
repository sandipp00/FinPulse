import { useSyncExternalStore } from 'react'
import { routeFor } from '../lib/routes'

function subscribe(callback) {
  window.addEventListener('popstate', callback)
  return () => window.removeEventListener('popstate', callback)
}

const currentPath = () => window.location.pathname

/**
 * Go to another page of the app without reloading it.
 *   replace   swap the current history entry instead of adding one
 *   scrollTo  id of an element the next page should scroll into view
 */
export function navigate(path, { replace = false, scrollTo } = {}) {
  window.history[replace ? 'replaceState' : 'pushState']({ scrollTo }, '', path)
  // pushState does not announce itself, so tell the subscribers ourselves.
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/** 'home' | 'signin' | 'signup', following the address bar (including Back/Forward). */
export function useRoute() {
  return routeFor(useSyncExternalStore(subscribe, currentPath, () => '/'))
}
