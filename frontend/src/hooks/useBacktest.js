import { useEffect, useState } from 'react'
import { getBacktest } from '../api/finpulse'

/** Backtest of the signal rules for one symbol and timeframe, with slippage and position size. */
export function useBacktest(symbol, interval, { slippageBps = 0, positionPct = 100 } = {}) {
  const [result, setResult] = useState({ key: null, data: null, error: '' })
  const key = `${symbol}|${interval}|${slippageBps}|${positionPct}`

  useEffect(() => {
    let cancelled = false

    getBacktest(symbol, interval, { slippageBps, positionPct })
      .then((data) => {
        if (!cancelled) setResult({ key, data, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setResult({ key, data: null, error: err.message || 'Unable to run backtest.' })
      })

    return () => {
      cancelled = true
    }
  }, [symbol, interval, slippageBps, positionPct, key])

  const loading = result.key !== key
  return {
    data: loading ? null : result.data,
    loading,
    error: loading ? '' : result.error,
  }
}
