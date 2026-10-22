import { useEffect, useState } from 'react'
import { getBacktest } from '../api/finpulse'

/** Backtest of the signal rules for one symbol and timeframe. */
export function useBacktest(symbol, interval) {
  const [result, setResult] = useState({ key: null, data: null, error: '' })
  const key = `${symbol}|${interval}`

  useEffect(() => {
    let cancelled = false

    getBacktest(symbol, interval)
      .then((data) => {
        if (!cancelled) setResult({ key, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ key, data: null, error: err.message || 'Unable to run backtest.' })
      })

    return () => {
      cancelled = true
    }
  }, [symbol, interval, key])

  const loading = result.key !== key
  return {
    data: loading ? null : result.data,
    loading,
    error: loading ? '' : result.error,
  }
}
