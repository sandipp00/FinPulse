import { useEffect, useState } from 'react'
import { getFxHistory, getFxPairs } from '../api/finpulse'

/** Every tracked FX pair with its latest ECB-based rate (/api/fx/pairs). */
export function useFxPairs() {
  const [state, setState] = useState({ data: null, loading: true, error: '' })

  useEffect(() => {
    let cancelled = false
    getFxPairs()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: err.message || 'Unable to load FX rates.' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}

/** Daily history for one pair; an empty pair loads nothing. */
export function useFxHistory(pair) {
  const [result, setResult] = useState({ pair: null, data: null, error: '' })

  useEffect(() => {
    if (!pair) return undefined
    let cancelled = false
    getFxHistory(pair)
      .then((data) => {
        if (!cancelled) setResult({ pair, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ pair, data: null, error: err.message || 'Unable to load the history.' })
      })
    return () => {
      cancelled = true
    }
  }, [pair])

  const loading = Boolean(pair) && result.pair !== pair
  return { data: loading ? null : result.data, loading, error: loading ? '' : result.error }
}
