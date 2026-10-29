import { useEffect, useState } from 'react'
import { getInstrumentHistory, getInstruments } from '../api/finpulse'

/** Every instrument the API can chart (/api/instruments). */
export function useInstruments() {
  const [state, setState] = useState({ instruments: [], loading: true, error: '' })

  useEffect(() => {
    let cancelled = false
    getInstruments()
      .then((response) => {
        if (!cancelled) setState({ instruments: response.instruments ?? [], loading: false, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState({ instruments: [], loading: false, error: err.message || 'Unable to load instruments.' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

/**
 * History for one instrument (/api/instruments/history). Pass an empty symbol to
 * load nothing. The result is kept with the request it answers, so a slow answer
 * for a previous selection is never shown under the new one.
 */
export function useInstrumentHistory(symbol, interval, limit) {
  const key = symbol ? `${symbol}|${interval}|${limit}` : ''
  const [result, setResult] = useState({ key: null, data: null, error: '' })
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    if (!key) return undefined
    let cancelled = false
    getInstrumentHistory(symbol, interval, limit)
      .then((data) => {
        if (!cancelled) setResult({ key, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ key, data: null, error: err.message || 'Unable to load history.' })
      })
    return () => {
      cancelled = true
    }
  }, [key, symbol, interval, limit, reloadCount])

  const loading = Boolean(key) && result.key !== key
  return {
    data: loading || !key ? null : result.data,
    loading,
    error: loading || !key ? '' : result.error,
    reload: () => setReloadCount((n) => n + 1),
  }
}
