import { useCallback, useEffect, useState } from 'react'
import { getWatchlist, saveWatchlist } from '../api/finpulse'

const STORAGE_KEY = 'finpulse.watchlist'

function readLocal() {
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY))
    return Array.isArray(value) && value.length > 0 ? value.filter((s) => typeof s === 'string') : null
  } catch {
    return null
  }
}

function writeLocal(symbols) {
  try {
    if (symbols.length) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols))
    else window.localStorage.removeItem(STORAGE_KEY)
    return true
  } catch {
    return false
  }
}

/**
 * The user's own watchlist symbols, or null for the default list. Signed in, it is
 * saved to the account (/api/watchlist); as a guest, in this browser only.
 * save([]) goes back to the default.
 */
export function useWatchlist(user) {
  const signedIn = Boolean(user)
  const [state, setState] = useState({ symbols: null, error: '', saving: false })

  useEffect(() => {
    let cancelled = false
    if (!signedIn) {
      setState({ symbols: readLocal(), error: '', saving: false })
      return undefined
    }
    getWatchlist()
      .then((data) => { if (!cancelled) setState({ symbols: data.has_custom ? data.symbols : null, error: '', saving: false }) })
      .catch((error) => { if (!cancelled) setState({ symbols: null, error: error.message || 'Could not load your watchlist', saving: false }) })
    return () => {
      cancelled = true
    }
  }, [signedIn, user?.id])

  const save = useCallback(async (symbols) => {
    setState((s) => ({ ...s, saving: true, error: '' }))
    try {
      if (signedIn) await saveWatchlist(symbols)
      else if (!writeLocal(symbols)) throw new Error('This browser does not allow saving the list')
      setState({ symbols: symbols.length ? symbols : null, error: '', saving: false })
      return true
    } catch (error) {
      setState((s) => ({ ...s, saving: false, error: error.message || 'Could not save the watchlist' }))
      return false
    }
  }, [signedIn])

  return { custom: state.symbols, error: state.error, saving: state.saving, save, signedIn }
}
