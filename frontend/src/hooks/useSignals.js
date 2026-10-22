import { useEffect, useState } from 'react'
import { getSignals } from '../api/finpulse'

// Ratings only change when a candle closes, so a slow poll is plenty.
const REFRESH_MS = 30_000

/** Buy/sell ratings for every live symbol at one timeframe. */
export function useSignals(interval) {
  const [result, setResult] = useState({ interval: null, signals: [], error: '' })

  useEffect(() => {
    let cancelled = false

    const load = () => {
      getSignals(interval)
        .then((response) => {
          if (cancelled) return
          setResult({ interval, signals: response.signals ?? [], error: '' })
        })
        .catch((err) => {
          if (cancelled) return
          // Keep showing the last good ratings if a refresh fails.
          setResult((current) => ({
            interval,
            signals: current.interval === interval ? current.signals : [],
            error: err.message || 'Unable to load signals.',
          }))
        })
    }

    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [interval])

  const loading = result.interval !== interval
  return {
    signals: loading ? [] : result.signals,
    loading,
    error: loading ? '' : result.error,
  }
}
