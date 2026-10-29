import { useCallback, useSyncExternalStore } from 'react'
import { buildExplorerQuery, parseExplorerQuery } from '../lib/explorer'

function subscribe(callback) {
  window.addEventListener('popstate', callback)
  return () => window.removeEventListener('popstate', callback)
}

const currentSearch = () => window.location.search

/**
 * The explorer's selection, kept in the address bar so a view can be bookmarked or
 * shared. Changes replace the history entry (no scroll jump, no Back step per click).
 */
export function useExplorerQuery() {
  const search = useSyncExternalStore(subscribe, currentSearch, () => '')
  const query = parseExplorerQuery(search)

  const setQuery = useCallback((next) => {
    const merged = { ...parseExplorerQuery(window.location.search), ...next }
    window.history.replaceState(null, '', `${window.location.pathname}${buildExplorerQuery(merged)}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, [])

  return [query, setQuery]
}
